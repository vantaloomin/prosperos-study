from typing import Literal

from fastapi import APIRouter, Query, Request

from server.memory.control_models import ControlSave
from server.memory.control_service import Controls
from server.memory.plan_edits import PlanEdit, Plans
from server.memory.plan_scan import PlanScanPreview, PlanScanStart
from server.memory.plan_scans import PlanScans
from server.memory.rehearsal import RehearsalRequest, Rehearsals

router = APIRouter(prefix='/api')


@router.get('/branches/{branch_id}/memory-controls')
def view(branch_id: str, request: Request):
    return Controls(request.app.state.database).view(branch_id)


@router.get('/branches/{branch_id}/memory-control-sources')
def sources(branch_id: str, request: Request, category: Literal['prose', 'library'] = 'prose', offset: int = Query(default=0, ge=0)):
    return Controls(request.app.state.database).sources(branch_id, category, offset)


@router.put('/branches/{branch_id}/memory-controls')
def save(branch_id: str, body: ControlSave, request: Request):
    return Controls(request.app.state.database).save(branch_id, body)


@router.get('/branches/{branch_id}/memory-control-history')
def history(branch_id: str, request: Request, offset: int = Query(default=0, ge=0)):
    return Controls(request.app.state.database).history(branch_id, offset)


@router.get('/branches/{branch_id}/memory-control-history/{version_id}')
def version(branch_id: str, version_id: str, request: Request):
    return Controls(request.app.state.database).version(branch_id, version_id)


@router.get('/branches/{branch_id}/memory-rehearsal')
def rehearsal_views(branch_id: str, request: Request):
    return Rehearsals(request.app.state.database).views(branch_id)


@router.post('/branches/{branch_id}/memory-rehearsal')
def rehearse(branch_id: str, body: RehearsalRequest, request: Request):
    return Rehearsals(request.app.state.database).search(branch_id, body)

@router.get('/branches/{branch_id}/plans')
def plans(branch_id: str, request: Request):
    return Plans(request.app.state.database).view(branch_id)


@router.get('/branches/{branch_id}/plan-sources')
def plan_sources(branch_id: str, request: Request, offset: int = Query(default=0, ge=0)):
    return Plans(request.app.state.database).sources(branch_id, offset)


@router.post('/branches/{branch_id}/plans')
def edit_plan(branch_id: str, body: PlanEdit, request: Request):
    return Plans(request.app.state.database).save(branch_id, body)


@router.post('/branches/{branch_id}/plan-reviews/preview')
def preview_plan_review(branch_id: str, body: PlanScanPreview, request: Request):
    return PlanScans(request.app.state.database).preview(branch_id, body)


@router.post('/branches/{branch_id}/plan-reviews', status_code=201)
async def start_plan_review(branch_id: str, body: PlanScanStart, request: Request):
    result = PlanScans(request.app.state.database).create(branch_id, body)
    for job_id in result['job_ids']:
        request.app.state.review_runner.start(job_id)
    return result


@router.get('/branches/{branch_id}/plan-reviews')
def plan_review_history(branch_id: str, request: Request):
    return PlanScans(request.app.state.database).history(branch_id)
