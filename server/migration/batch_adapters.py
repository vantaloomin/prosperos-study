from pydantic import ValidationError

from server.archives.format import ArchiveRestore
from server.archives.service import Archives
from server.database import decode
from server.errors import DomainError
from server.library_formats.import_conversion import source_bytes
from server.library_formats.import_duplicates import publication_payload
from server.library_formats.import_models import ImportPublish, ImportUpload
from server.library_formats.imports import LibraryImports
from server.library_formats.markdown import read_json
from server.migration.models import TranscriptPublish, TranscriptUpload
from server.migration.preset_models import PresetPublish, PresetUpload
from server.migration.presets import PresetImports
from server.migration.transcripts import TranscriptImports
from server.operations import previous
from server.writing.bundle_models import BundleImport, BundlePreview
from server.writing.bundles import import_bundle, prepare_bundle

SERVICES = {'library': (LibraryImports, ImportUpload, ImportPublish),
            'transcript': (TranscriptImports, TranscriptUpload, TranscriptPublish),
            'preset': (PresetImports, PresetUpload, PresetPublish)}


def model_input(model, value):
    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise DomainError('; '.join(item['msg'] for item in error.errors()), 400) from None


def native_document(row):
    return read_json(source_bytes(row['source_base64']).decode('utf-8-sig'))


def stage_item(database, row):
    kind = row['kind']
    if kind in SERVICES:
        service, upload, _ = SERVICES[kind]
        name = decode(row['candidates'])[kind]['filename']
        return service(database).stage(model_input(upload, {'filename': name, 'source_base64': row['source_base64']}))['id']
    if kind == 'archive':
        return Archives(database).stage(source_bytes(row['source_base64']).decode('utf-8-sig'))['id']
    return row['id']


def preview_item(database, row, mappings=None):
    kind = row['kind']
    if kind in SERVICES:
        return SERVICES[kind][0](database).view(row['import_id'])
    if kind == 'archive':
        return Archives(database).review(row['import_id'])
    with database.connect() as connection:
        return prepare_bundle(connection, BundlePreview(document=native_document(row), mappings=mappings or {}))[0]


def publish_item(database, row, choices):
    payload = {**choices, 'operation_id': 'migration-batch-' + row['id']}
    kind = row['kind']
    if kind in SERVICES:
        service, _, publish = SERVICES[kind]
        return service(database).publish(row['import_id'], model_input(publish, payload))
    if kind == 'archive':
        return Archives(database).apply(row['import_id'], model_input(ArchiveRestore, payload))
    # The reviewed staged source is authoritative; callers cannot swap the file.
    payload['document'] = native_document(row)
    return import_bundle(database, model_input(BundleImport, payload))


def saved_publication(database, row, choices):
    operation_id = 'migration-batch-' + row['id']
    payload = {**choices, 'operation_id': operation_id}
    kind = row['kind']
    if kind in SERVICES:
        body = model_input(SERVICES[kind][2], payload)
        payload = publication_payload(row['import_id'], body) if kind == 'library' else {'import_id': row['import_id'], **body.model_dump(exclude={'operation_id'})}
        operation_kind = {'library': 'library-import', 'preset': 'preset-import', 'transcript': 'transcript-import'}[kind]
    else:
        payload.pop('duplicate_action', None)
        operation_kind = 'archive-restore' if kind == 'archive' else 'writing-bundle-import'
        payload = native_operation_payload(row, payload)
    with database.connect() as connection:
        return previous(connection, operation_id, operation_kind, payload)


def native_operation_payload(row, payload):
    if row['kind'] == 'archive':
        body = model_input(ArchiveRestore, payload)
        return {'archive_id': row['import_id'], 'sha256': body.sha256}
    return model_input(BundleImport, {**payload, 'document': native_document(row)}).model_dump()
