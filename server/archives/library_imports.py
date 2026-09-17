from server.archives.records import related_rows
from server.character_content import canonical_kind
from server.database import decode, many
from server.errors import require
from server.library_formats.import_files import materialize_import
from server.library_formats.import_models import ImportUpload
from server.library_formats.imports import validated_conversion


def collect_imports(connection, data):
    data['asset_import_origins'] = related_rows(connection, 'asset_import_origins', 'version_id', {row['id'] for row in data['asset_versions']})
    data['library_imports'] = related_rows(connection, 'library_imports', 'id', {row['import_id'] for row in data['asset_import_origins']})


def validate_imports(connection, data):
    for row in data['library_imports']:
        upload = ImportUpload(filename=row['filename'], source_base64=row['source_base64'])
        expected = validated_conversion(upload.filename, upload.source_base64)
        require(row['source_sha256'] == expected['source_sha256'] and decode(row['conversion']) == expected,
                'An imported source or its converted Markdown does not match the preserved original.')
    rows = many(connection, 'SELECT o.part,a.kind,i.conversion FROM asset_import_origins o '
                'JOIN asset_versions v ON v.id=o.version_id JOIN assets a ON a.id=v.asset_id '
                'JOIN library_imports i ON i.id=o.import_id')
    for row in rows:
        parts = {item['part'] for item in decode(row['conversion'])['drafts']}
        require(row['part'] == canonical_kind(row['kind']) and row['part'] in parts, 'Import provenance refers to the wrong kind of Library item.')


def restore_imports(database, document, mapping):
    for row in document['data']['library_imports']:
        materialize_import(database, {**row, 'id': mapping[row['id']]}, decode(row['conversion']))
