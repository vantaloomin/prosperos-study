"""Disposable, content-addressed local index. Never an authority for source scope."""
import hashlib
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ACTIVE_INDEX = ContextVar('memory_index', default=None)
MAX_INDEX_BYTES = 128 * 1024 * 1024
MAX_ENTRY_BYTES = 2 * 1024 * 1024


class SourceIndex:
    def __init__(self, path, limit=MAX_INDEX_BYTES):
        self.path = Path(path)
        self.limit = limit
        self.connection = None
        self.pending = {}
        self.pending_bytes = 0
        self.hits = self.misses = self.writes = 0
        self.needs_vacuum = False

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=0.05, isolation_level=None)
        self.connection = connection
        connection.execute('PRAGMA auto_vacuum=INCREMENTAL')
        connection.execute(f'PRAGMA max_page_count={(self.limit + 4 * 1024 * 1024) // 4096}')
        connection.execute('CREATE TABLE IF NOT EXISTS entries '
                           '(key TEXT PRIMARY KEY,payload BLOB NOT NULL,digest TEXT NOT NULL,size INTEGER NOT NULL)')
        connection.execute('BEGIN')

    def get(self, key):
        if key in self.pending:
            return self.pending[key]
        try:
            row = self.connection.execute('SELECT payload,digest FROM entries WHERE key=?', (key,)).fetchone()
            if row and len(row[0]) <= MAX_ENTRY_BYTES and hashlib.sha256(key.encode() + row[0]).hexdigest() == row[1]:
                self.hits += 1
                return row[0]
        except (sqlite3.Error, AttributeError, TypeError):
            pass
        self.misses += 1
        return None

    def put(self, key, payload):
        if len(payload) > min(MAX_ENTRY_BYTES, self.limit // 4):
            return
        previous = self.pending.get(key, b'')
        self.pending[key] = payload
        self.pending_bytes += len(payload) - len(previous)
        if len(self.pending) >= 2048 or self.pending_bytes >= min(4 * 1024 * 1024, self.limit // 2):
            self.flush()

    def flush(self):
        if not self.pending or self.connection is None:
            return
        try:
            self.connection.commit()
            self.connection.execute('BEGIN IMMEDIATE')
            rows = [(key, value, hashlib.sha256(key.encode() + value).hexdigest(), len(value) + 256)
                    for key, value in self.pending.items()]
            self.prune(sum(row[3] for row in rows))
            self.connection.executemany('INSERT OR REPLACE INTO entries VALUES (?,?,?,?)', rows)
            self.connection.commit()
            self.writes += len(rows)
        except sqlite3.Error:
            self.connection.rollback()
        finally:
            self.pending.clear()
            self.pending_bytes = 0
            self.connection.execute('BEGIN')

    def prune(self, incoming):
        size = self.connection.execute('SELECT COALESCE(SUM(size),0) FROM entries').fetchone()[0]
        if size + incoming <= self.limit:
            return
        # FIFO disk eviction; the process cache separately keeps recently used objects.
        removed, ids = 0, []
        for row_id, entry_size in self.connection.execute('SELECT rowid,size FROM entries ORDER BY rowid'):
            ids.append((row_id,))
            removed += entry_size
            if size - removed + incoming <= self.limit:
                break
        self.connection.executemany('DELETE FROM entries WHERE rowid=?', ids)
        self.needs_vacuum = True

    def close(self):
        try:
            self.flush()
            if self.connection is not None:
                self.connection.commit()
                if self.needs_vacuum:
                    self.connection.execute('PRAGMA incremental_vacuum(128)')
        except sqlite3.Error:
            pass
        finally:
            if self.connection is not None:
                self.connection.close()


@contextmanager
def index_session(path, *, limit=MAX_INDEX_BYTES):
    index = SourceIndex(path, limit)
    try:
        index.open()
    except (OSError, sqlite3.Error):
        index.close()
        yield None
        return
    token = ACTIVE_INDEX.set(index)
    try:
        yield index
    finally:
        ACTIVE_INDEX.reset(token)
        index.close()


@contextmanager
def connection_index(connection, enabled=True):
    if not enabled:
        yield None
        return
    filename = next((row[2] for row in connection.execute('PRAGMA database_list') if row[1] == 'main'), '')
    if not filename:
        yield None
        return
    database = Path(filename)
    with index_session(database.parent / '.cache' / (database.name + '.memory.sqlite3')) as index:
        yield index
