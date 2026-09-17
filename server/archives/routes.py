from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from server.archives.format import ArchiveCreate, ArchiveRestore, ArchiveUpload
from server.archives.service import Archives

router = APIRouter(prefix="/api/archives")


@router.get("")
def list_archives(request: Request):
    return Archives(request.app.state.database).list()


@router.post("", status_code=201)
def create_archive(body: ArchiveCreate, request: Request):
    return Archives(request.app.state.database).create(body)


@router.post("/imports", status_code=201)
def stage_import(body: ArchiveUpload, request: Request):
    return Archives(request.app.state.database).stage(body.content)


@router.get("/{file_id}/download")
def download_archive(file_id: str, request: Request):
    row, path = Archives(request.app.state.database).file(file_id)
    return FileResponse(path, media_type="application/json", filename=row["filename"],
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{file_id}/restore")
def restore_archive(file_id: str, body: ArchiveRestore, request: Request):
    return Archives(request.app.state.database).apply(file_id, body)
