from fastapi import APIRouter, Query, Request

from server.memory.maintenance_models import (
    BackfillPreview,
    BackfillStart,
    BatchResume,
    MaintenanceResume,
)
from server.memory.maintenance_service import Maintenance

router = APIRouter(prefix='/api')


@router.post('/branches/{branch_id}/summary-backfill-preview')
def preview(branch_id: str, body: BackfillPreview, request: Request):
    return Maintenance(request.app.state.database).preview(branch_id, body)


@router.post('/branches/{branch_id}/summary-backfill', status_code=201)
def start(branch_id: str, body: BackfillStart, request: Request):
    return Maintenance(request.app.state.database).create(branch_id, body)


@router.get('/branches/{branch_id}/summary-maintenance')
def status(branch_id: str, request: Request):
    return Maintenance(request.app.state.database).status(branch_id)


@router.post('/branches/{branch_id}/summary-maintenance/resume')
def resume_waiting(branch_id: str, body: MaintenanceResume, request: Request):
    return Maintenance(request.app.state.database).resume_waiting(branch_id, body)


@router.get('/branches/{branch_id}/summary-batches')
def history(branch_id: str, request: Request, offset: int = Query(default=0, ge=0)):
    return Maintenance(request.app.state.database).history(branch_id, offset)


@router.get('/summary-batches/{batch_id}')
def detail(batch_id: str, request: Request):
    return Maintenance(request.app.state.database).detail(batch_id)


@router.post('/summary-batches/{batch_id}/stop')
async def stop(batch_id: str, request: Request):
    return request.app.state.maintenance_runner.stop(batch_id)


@router.post('/summary-batches/{batch_id}/resume')
async def resume(batch_id: str, body: BatchResume, request: Request):
    return request.app.state.maintenance_runner.resume(batch_id, body)
