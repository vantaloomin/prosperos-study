from fastapi import APIRouter, Request

from server.background.interpretation_models import (
    InterpretationChoice,
    InterpretationPreview,
    InterpretationStart,
)
from server.background.interpretations import Interpretations

router = APIRouter(prefix='/api')


@router.post('/branches/{branch_id}/background/interpretations/preview')
def preview(branch_id: str, body: InterpretationPreview, request: Request):
    return Interpretations(request.app.state.database).preview(branch_id, body)


@router.post('/branches/{branch_id}/background/interpretations', status_code=201)
async def start(branch_id: str, body: InterpretationStart, request: Request):
    result = Interpretations(request.app.state.database).create(branch_id, body)
    for job_id in result['job_ids']:
        request.app.state.background_runner.start(job_id)
    return result


@router.get('/branches/{branch_id}/background/interpretations')
def history(branch_id: str, request: Request):
    return Interpretations(request.app.state.database).list(branch_id)


@router.get('/background-interpretations/{run_id}')
def detail(run_id: str, request: Request, reveal: bool = False):
    return Interpretations(request.app.state.database).detail(run_id, reveal)


@router.post('/background-jobs/{job_id}/choose')
def choose(job_id: str, body: InterpretationChoice, request: Request):
    return Interpretations(request.app.state.database).choose(job_id, body)


@router.post('/background-jobs/{job_id}/stop')
async def stop(job_id: str, request: Request):
    return request.app.state.background_runner.cancel(job_id)


@router.post('/background-jobs/{job_id}/retry')
async def retry(job_id: str, request: Request):
    return request.app.state.background_runner.retry(job_id)


@router.get('/background-jobs/{job_id}/attempts/reveal')
def attempts(job_id: str, request: Request):
    return Interpretations(request.app.state.database).attempts(job_id)
