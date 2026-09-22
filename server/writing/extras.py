"""Unsupported import settings remain visible data, outside executable guidance."""
import json

from server.database import decode, encode
from server.errors import require

MAX_EXTRAS = 512 * 1024
PRIVATE_KEYS = {'api_key', 'apikey', 'access_token', 'refresh_token', 'token', 'password',
                'secret', 'credential_ref', 'credentials', 'authorization', 'base_url', 'endpoint'}


def validate_extras(value):
    require(isinstance(value, dict), 'Unsupported settings must be a JSON object.')
    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        require(False, 'Unsupported settings must be finite JSON data.')
    require(len(encoded.encode('utf-8')) <= MAX_EXTRAS, 'Unsupported settings are limited to 512 KiB.')
    return value


def read_extras(connection, version_id):
    row = connection.execute('SELECT content FROM writing_extras WHERE version_id=?', (version_id,)).fetchone()
    return decode(row['content']) if row else {}


def save_extras(connection, version_id, value):
    if validate_extras(value):
        connection.execute('INSERT INTO writing_extras VALUES (?,?)', (version_id, encode(value)))


def portable_metadata(value):
    if isinstance(value, dict):
        return {key: '[private connection field omitted]' if key.rsplit('.', 1)[-1].casefold().replace('-', '_') in PRIVATE_KEYS else portable_metadata(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [portable_metadata(item) for item in value]
    return value
