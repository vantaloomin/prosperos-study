from urllib.parse import quote

from fastapi import APIRouter, Request, Response

from server.inspiration.pack_models import PackExport, PackImport, PackUpload
from server.inspiration.packs import Packs
from server.inspiration.starters import starters

router = APIRouter(prefix='/api/inspiration', tags=['inspiration'])


@router.get('/starters')
def starter_packs():
    return starters()


@router.post('/packs', status_code=201)
def stage(body: PackUpload, request: Request):
    return Packs(request.app.state.database).stage(body)


@router.post('/packs/export')
def export(body: PackExport, request: Request):
    return Packs(request.app.state.database).export(body)


@router.get('/packs/{import_id}')
def review(import_id: str, request: Request):
    return Packs(request.app.state.database).view(import_id)


@router.get('/packs/{import_id}/original')
def original(import_id: str, request: Request):
    filename, source = Packs(request.app.state.database).original(import_id)
    return Response(source, media_type='application/octet-stream', headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename, safe='')}", 'X-Content-Type-Options': 'nosniff'})


@router.post('/packs/{import_id}/publish', status_code=201)
def publish(import_id: str, body: PackImport, request: Request):
    return Packs(request.app.state.database).publish(import_id, body)


@router.get('/versions/{version_id}/imports')
def origins(version_id: str, request: Request):
    return Packs(request.app.state.database).origins(version_id)
