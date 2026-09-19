"""Disposable vectors keyed by exact bytes and saved embedding configuration."""
import json

from server.database import encode
from server.errors import DomainError, require
from server.memory.index import index_session
from server.memory.writer_recall import digest
from server.providers.embeddings import unit_vector

MAX_VECTOR_VALUES = 2_000_000


def embedding_identity(profile):
    config = profile['config']
    return {'provider': config['provider'], 'base_url': config['base_url'],
            'model': config.get('embedding_model', ''), 'profile_version': profile.get('number', 0),
            'algorithm': 'unit-cosine-v1',
            **({'input_format': config['embedding_input_format']}
               if config.get('embedding_input_format', 'plain') != 'plain' else {})}


def cache_key(identity, source):
    return 'embedding-v1:' + digest(encode(identity)) + ':' + source['sha256']


def cache_path(provider):
    database = getattr(provider, 'database', None)
    if database is None:
        return None
    return database.path.parent / '.cache' / (database.path.name + '.memory.sqlite3')


def read_vectors(path, identity, sources):
    if path is None:
        return {}
    result = {}
    values = 0
    with index_session(path) as index:
        if index is None:
            return result
        for source in sources:
            payload = index.get(cache_key(identity, source))
            if payload is None:
                continue
            try:
                row = json.loads(payload)
                if isinstance(row.get('model'), str) and 0 < len(row['model']) <= 300:
                    vector = unit_vector(row['vector'])
                    result[source['id']] = {'vector': vector, 'model': row['model']}
                    values += len(vector)
            except (ValueError, KeyError, TypeError, AttributeError, DomainError):
                continue
            require(values <= MAX_VECTOR_VALUES, 'Semantic vectors exceed the memory limit; keyword search retained.', 409)
    return result


def write_vectors(path, identity, sources, rows):
    if path is None:
        return
    with index_session(path) as index:
        if index is not None:
            for source in sources:
                index.put(cache_key(identity, source), encode(rows[source['id']]).encode('utf-8'))
