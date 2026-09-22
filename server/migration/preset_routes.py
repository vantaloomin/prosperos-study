from pathlib import PureWindowsPath

from fastapi import APIRouter, Request

from server.database import decode, encode
from server.library_formats.import_conversion import source_bytes
from server.migration.preset_models import PresetConfiguration, PresetPublish, PresetUpload
from server.migration.presets import PresetImports
from server.migration.routes import attachment

router = APIRouter(prefix='/api')


@router.get('/migration/presets')
def list_imports(request: Request):
    return PresetImports(request.app.state.database).list()


@router.post('/migration/presets', status_code=201)
def stage(body: PresetUpload, request: Request):
    return PresetImports(request.app.state.database).stage(body)


@router.get('/migration/presets/{import_id}')
def view(import_id: str, request: Request):
    return PresetImports(request.app.state.database).view(import_id)


@router.post('/migration/presets/{import_id}/configuration-preview')
def configuration(import_id: str, body: PresetConfiguration, request: Request):
    return PresetImports(request.app.state.database).configure(import_id, body)


@router.post('/migration/presets/{import_id}/publish', status_code=201)
def publish(import_id: str, body: PresetPublish, request: Request):
    return PresetImports(request.app.state.database).publish(import_id, body)


@router.get('/migration/presets/{import_id}/original')
def original(import_id: str, request: Request):
    row = PresetImports(request.app.state.database).row(import_id)
    return attachment(source_bytes(row['source_base64']), PureWindowsPath(row['filename']).name)


@router.get('/migration/presets/{import_id}/report')
def report(import_id: str, request: Request):
    return attachment(encode(decode(PresetImports(request.app.state.database).row(import_id)['conversion'])), 'preset-conversion.json')


@router.get('/writing-versions/{version_id}/imports')
def origins(version_id: str, request: Request):
    return PresetImports(request.app.state.database).origins(version_id)
