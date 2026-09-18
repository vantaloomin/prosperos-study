from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from server.memory.summary_models import SummaryPreview, SummaryPublish, SummaryStart
from server.memory.summary_service import Summaries

router = APIRouter(prefix='/api')


@router.get('/branches/{branch_id}/summary-sources')
def sources(branch_id: str, request: Request, offset: int = Query(default=0, ge=0)):
    return Summaries(request.app.state.database).sources(branch_id, offset)


@router.post('/branches/{branch_id}/summary-preview')
def preview(branch_id: str, body: SummaryPreview, request: Request):
    return Summaries(request.app.state.database).preview(branch_id, body)


@router.post('/branches/{branch_id}/summaries', status_code=201)
async def start(branch_id: str, body: SummaryStart, request: Request):
    result = await run_in_threadpool(Summaries(request.app.state.database).create, branch_id, body)
    for job_id in result['job_ids']:
        request.app.state.summary_runner.start(job_id)
    return result


@router.get('/branches/{branch_id}/summaries')
def history(branch_id: str, request: Request, offset: int = Query(default=0, ge=0)):
    return Summaries(request.app.state.database).history(branch_id, offset)


@router.get('/summaries/{run_id}')
def detail(run_id: str, branch_id: str, request: Request):
    return Summaries(request.app.state.database).detail(run_id, branch_id)


@router.post('/summaries/{run_id}/versions', status_code=201)
def publish(run_id: str, body: SummaryPublish, request: Request):
    return Summaries(request.app.state.database).publish(run_id, body)


@router.get('/summary-jobs/{job_id}/attempts')
def attempts(job_id: str, request: Request):
    return Summaries(request.app.state.database).attempts(job_id)


@router.post('/summary-jobs/{job_id}/stop')
async def stop(job_id: str, request: Request):
    return request.app.state.summary_runner.cancel(job_id)


@router.post('/summary-jobs/{job_id}/retry')
async def retry(job_id: str, request: Request):
    return request.app.state.summary_runner.retry(job_id)
