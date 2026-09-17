from urllib.parse import quote

from fastapi import APIRouter, Request, Response

from server.library_formats.service import MarkdownLibrary, SourceRecovery

router = APIRouter(prefix='/api')


@router.get('/library/{asset_id}/markdown')
def source(asset_id: str, request: Request, version_id: str | None = None):
    return MarkdownLibrary(request.app.state.database).view(asset_id, version_id)


@router.post('/library/{asset_id}/markdown/recover')
def recover_source(asset_id: str, body: SourceRecovery, request: Request):
    return MarkdownLibrary(request.app.state.database).recover(asset_id, body)


@router.get('/versions/{version_id}/markdown')
def download_source(version_id: str, request: Request):
    source, _path = MarkdownLibrary(request.app.state.database).download(version_id)
    filename = quote(source['name'] + '.md', safe='')
    return Response(source['markdown'].encode('utf-8'), media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})
