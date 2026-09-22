from fastapi import APIRouter, Request

from server.backups.models import BackupNow, BackupSettings

router = APIRouter(prefix='/api/backups')


@router.get('/settings')
def settings(request: Request):
    return request.app.state.backups.settings()


@router.put('/settings')
def configure(body: BackupSettings, request: Request):
    return request.app.state.backups.configure(body)


@router.get('')
def history(request: Request):
    return request.app.state.backups.history()


@router.post('', status_code=201)
def backup_now(body: BackupNow, request: Request):
    return request.app.state.backups.run(body)


@router.post('/{identity}/review')
def review(identity: str, request: Request):
    return request.app.state.backups.review(identity)
