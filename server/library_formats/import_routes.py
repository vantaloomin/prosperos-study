from urllib.parse import quote

from fastapi import APIRouter, Request, Response

from server.database import decode
from server.errors import require
from server.library_formats.import_conversion import source_bytes
from server.library_formats.import_files import package_zip
from server.library_formats.import_models import ImportPublish, ImportUpload
from server.library_formats.imports import LibraryImports

router = APIRouter(prefix='/api')


@router.post('/library-imports', status_code=201)
def stage(body: ImportUpload, request: Request):
    return LibraryImports(request.app.state.database).stage(body)


@router.get('/library-imports/{import_id}')
def view(import_id: str, request: Request):
    return LibraryImports(request.app.state.database).view(import_id)


@router.post('/library-imports/{import_id}/publish', status_code=201)
def publish(import_id: str, body: ImportPublish, request: Request):
    return LibraryImports(request.app.state.database).publish(import_id, body)


@router.get('/library-imports/{import_id}/document')
def document(import_id: str, path: str, request: Request):
    row = LibraryImports(request.app.state.database).row(import_id)
    files = decode(row['conversion'])['files']
    require(path in files, 'This document is not in the converted package.', 404)
    return {'path': path, 'markdown': files[path]}


@router.get('/library-imports/{import_id}/original')
def original(import_id: str, request: Request):
    row = LibraryImports(request.app.state.database).row(import_id)
    return Response(source_bytes(row['source_base64']), media_type='application/octet-stream',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(row['filename'], safe='')}"})


@router.get('/library-imports/{import_id}/package')
def package(import_id: str, request: Request):
    row = LibraryImports(request.app.state.database).row(import_id)
    return Response(package_zip(row, decode(row['conversion'])), media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename="converted-library.zip"'})


@router.get('/versions/{version_id}/imports')
def origins(version_id: str, request: Request):
    return LibraryImports(request.app.state.database).origins(version_id)
