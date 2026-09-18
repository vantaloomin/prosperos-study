"""Byte-bounded process memoization with optional JSON-only persistent backing."""
import hashlib
import json
import sys
from collections import OrderedDict
from dataclasses import fields, is_dataclass
from functools import wraps
from threading import RLock

from server.memory.index import ACTIVE_INDEX


def children(value):
    if isinstance(value, dict):
        return (*value.keys(), *value.values())
    if isinstance(value, (tuple, list, set, frozenset)):
        return value
    if is_dataclass(value):
        return tuple(getattr(value, field.name) for field in fields(value))
    return ()


def retained_bytes(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    overhead = sys.getsizeof(vars(value)) if is_dataclass(value) and hasattr(value, '__dict__') else 0
    return sys.getsizeof(value) + overhead + sum(retained_bytes(item, seen) for item in children(value))


class ByteCache:
    def __init__(self, limit):
        self.limit = limit
        self.values = OrderedDict()
        self.bytes = self.hits = self.misses = 0
        self.lock = RLock()

    def get(self, key):
        with self.lock:
            entry = self.values.get(key)
            if entry is None:
                self.misses += 1
                return None
            self.hits += 1
            self.values.move_to_end(key)
            return entry[0]

    def put(self, key, value):
        size = retained_bytes((key, value)) + 192  # OrderedDict entry and bookkeeping allowance.
        with self.lock:
            previous = self.values.pop(key, None)
            self.bytes -= previous[1] if previous else 0
            if size > self.limit:
                return
            while self.values and self.bytes + size > self.limit:
                _, removed = self.values.popitem(last=False)
                self.bytes -= removed[1]
            self.values[key] = (value, size)
            self.bytes += size

    def clear(self):
        with self.lock:
            self.values.clear()
            self.bytes = self.hits = self.misses = 0

    def info(self):
        with self.lock:
            return {'entries': len(self.values), 'bytes': self.bytes, 'limit': self.limit,
                    'hits': self.hits, 'misses': self.misses}


def disk_key(namespace, args, kwargs):
    identity = json.dumps([namespace, args, kwargs], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


def immutable_text(value):
    # Only the exact immutable argument shapes used by text/chunk compilation.
    # Other JSON-compatible inputs retain the previous canonical identity.
    return type(value) is str or (type(value) is tuple and all(type(item) is str for item in value))


def process_key(namespace, args, kwargs):
    if all(immutable_text(value) for value in (*args, *kwargs.values())):
        return args, tuple(kwargs.items())
    return disk_key(namespace, args, kwargs)


def memoized(namespace, limit, *, dump=None, load=None):
    cache = ByteCache(limit)

    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            key = process_key(namespace, args, kwargs)
            value = cache.get(key)
            if value is not None:
                return value
            index = ACTIVE_INDEX.get() if dump and load else None
            persistent_key = disk_key(namespace, args, kwargs) if index else None
            payload = index.get(persistent_key) if index else None
            value = restore(payload, load) if payload is not None else None
            if value is None:
                value = function(*args, **kwargs)
                if index:
                    index.put(persistent_key, json.dumps(dump(value), ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            cache.put(key, value)
            return value

        call.cache_clear = cache.clear
        call.cache_info = cache.info
        return call
    return decorate


def restore(payload, load):
    try:
        return load(json.loads(payload))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None
