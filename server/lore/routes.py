from fastapi import APIRouter, Request, Response

from server.library_formats.service import SourceRecovery
from server.lore.files import EntryLibrary
from server.lore.imports import import_candidates, import_entry
from server.lore.inspection import inspect_branch
from server.lore.models import LorePreview
from server.lore.preview import preview_lore

router = APIRouter(prefix='/api')


@router.get('/branches/{branch_id}/lore')
def branch_lore(branch_id: str, request: Request):
    return inspect_branch(request.app.state.database, branch_id)


@router.get('/versions/{version_id}/imported-entries')
def candidates(version_id: str, request: Request):
    return import_candidates(request.app.state.database, version_id)


@router.get('/versions/{version_id}/imported-entry')
def imported_entry(version_id: str, import_id: str, path: str, request: Request):
    return import_entry(request.app.state.database, version_id, import_id, path)


@router.post('/lore/preview')
def preview(body: LorePreview):
    return preview_lore(body)


@router.get('/versions/{version_id}/entry-files')
def files(version_id: str, request: Request):
    return EntryLibrary(request.app.state.database).view(version_id)


@router.get('/versions/{version_id}/entry-file')
def proposal(version_id: str, entry_id: str, request: Request):
    return EntryLibrary(request.app.state.database).proposal(version_id, entry_id)


@router.get('/versions/{version_id}/entry-download')
def download(version_id: str, entry_id: str, request: Request):
    source = EntryLibrary(request.app.state.database).download(version_id, entry_id)
    return Response(source['markdown'].encode('utf-8'), media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="lore-entry.md"'})


@router.post('/versions/{version_id}/entry-recover')
def recover(version_id: str, entry_id: str, body: SourceRecovery, request: Request):
    return EntryLibrary(request.app.state.database).recover(version_id, entry_id, body)
