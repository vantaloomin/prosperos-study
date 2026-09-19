from hashlib import sha256

from server.database import decode, many, one
from server.errors import require
from server.library_formats.markdown import read_document
from server.lore.import_rules import native_keywords
from server.lore.models import LoreEntry


def imported_documents(connection, version_id):
    rows = many(connection, 'SELECT i.* FROM asset_import_origins o JOIN library_imports i ON i.id=o.import_id '
                'WHERE o.version_id=? AND o.part=? ORDER BY i.created_at', (version_id, 'lorebook'))
    result = []
    for row in rows:
        for path, markdown in decode(row['conversion'])['files'].items():
            if path.startswith('lorebook/entries/'):
                metadata, text = read_document(markdown)
                fields = metadata.get('source_fields', {})
                title = fields.get('name') or fields.get('comment') or fields.get('displayName') or f"Entry {metadata['source_index'] + 1}"
                result.append({'import_id': row['id'], 'filename': row['filename'], 'path': path,
                               'title': str(title)[:160], 'text': text, 'fields': fields,
                               'source_format': metadata.get('source_format'),
                               'id': sha256(f"{row['source_sha256']}:{path}".encode()).hexdigest()})
    return result


def import_candidates(database, version_id):
    with database.connect() as connection:
        one(connection, 'SELECT id FROM asset_versions WHERE id=?', (version_id,))
        return [{key: item[key] for key in ('import_id', 'filename', 'path', 'title', 'id')}
                for item in imported_documents(connection, version_id)]


def safe_keywords(value):
    return isinstance(value, list) and len(value) <= 64 and all(isinstance(term, str) and 0 < len(term.strip()) <= 200 for term in value)


def import_entry(database, version_id, import_id, path):
    with database.connect() as connection:
        item = next((item for item in imported_documents(connection, version_id)
                     if item['import_id'] == import_id and item['path'] == path), None)
    require(item is not None, 'Choose an imported entry belonging to this book version.', 404)
    require(len(item['text']) <= 100000, 'This preserved entry exceeds the editor limit. Split its prose into smaller entries.')
    fields = item['fields']
    keys, constant = native_keywords(fields, item['source_format'])
    supported_keys = keys if safe_keywords(keys) and not fields.get('use_regex') else []
    keyword_activation = bool(supported_keys) and not constant
    entry = LoreEntry(id=item['id'], title=item['title'] or 'Imported entry', text=item['text'], enabled=False,
                      activation='keywords' if keyword_activation else 'always', keywords=supported_keys)
    return {'entry': entry.model_dump(), 'original_fields': fields,
            'notice': 'Added entries start off. Only plain primary keywords and always-on flags are proposed; review all native rules and matching defaults before enabling. '
                      'Secondary conditions, regex, position/order, timing, probability, extensions, macros and decorators are not translated. '
                      'Exact original fields and prose remain in the preserved import package.'}
