from pathlib import PureWindowsPath

from fastapi import APIRouter, Request

from server.database import decode, encode
from server.errors import require
from server.library_formats.import_conversion import source_bytes
from server.migration.batch_models import (
    BatchBundlePreview,
    BatchPublish,
    BatchResolve,
    BatchRevision,
    BatchSkip,
    BatchUpload,
)
from server.migration.batch_publication import publish_batch_item, retry_batch_item
from server.migration.batches import MigrationBatches
from server.migration.routes import attachment

router = APIRouter(prefix='/api/migration')


@router.get('/batches')
def batches(request: Request):
    return MigrationBatches(request.app.state.database).list()


@router.post('/batches', status_code=201)
def stage_batch(body: BatchUpload, request: Request):
    return MigrationBatches(request.app.state.database).stage(body)


@router.get('/batches/{batch_id}')
def batch(batch_id: str, request: Request):
    return MigrationBatches(request.app.state.database).view(batch_id)


@router.post('/batch-items/{item_id}/interpretation')
def resolve(item_id: str, body: BatchResolve, request: Request):
    return MigrationBatches(request.app.state.database).resolve(item_id, body)


@router.put('/batch-items/{item_id}/selection')
def selection(item_id: str, body: BatchSkip, request: Request):
    return MigrationBatches(request.app.state.database).skip(item_id, body)


@router.get('/batch-items/{item_id}/preview')
def preview(item_id: str, request: Request):
    return MigrationBatches(request.app.state.database).preview(item_id)


@router.post('/batch-items/{item_id}/bundle-preview')
def bundle_preview(item_id: str, body: BatchBundlePreview, request: Request):
    service = MigrationBatches(request.app.state.database)
    require(service.row(item_id)['kind'] == 'writing-bundle', 'Choose a writing bundle.')
    return service.preview(item_id, body.mappings)


@router.post('/batch-items/{item_id}/publish', status_code=201)
def publish(item_id: str, body: BatchPublish, request: Request):
    return publish_batch_item(request.app.state.database, item_id, body)


@router.post('/batch-items/{item_id}/retry', status_code=201)
def retry(item_id: str, body: BatchRevision, request: Request):
    return retry_batch_item(request.app.state.database, item_id, body)


@router.get('/batch-items/{item_id}/original')
def original(item_id: str, request: Request):
    row = MigrationBatches(request.app.state.database).row(item_id)
    require(bool(row['source_base64']), 'Rejected input bytes were not retained.', 404)
    return attachment(source_bytes(row['source_base64']), PureWindowsPath(row['filename']).name)


@router.get('/batch-items/{item_id}/report')
def report(item_id: str, request: Request):
    row = MigrationBatches(request.app.state.database).row(item_id)
    fields = ('filename', 'source_sha256', 'kind', 'status', 'error')
    value = {key: row[key] for key in fields} | {key: decode(row[key]) for key in ('candidates', 'publication', 'result')}
    return attachment(encode(value), 'migration-item-report.json')
