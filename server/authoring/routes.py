from fastapi import APIRouter, Query, Request

from server.authoring.models import AuthoringDefault, AuthoringPreview, AuthoringStart
from server.authoring.service import Authoring

router = APIRouter(prefix='/api')


@router.get('/authoring/defaults')
def defaults(request: Request):
    return Authoring(request.app.state.database).defaults()


@router.put('/authoring/defaults')
def save_default(body: AuthoringDefault, request: Request):
    return Authoring(request.app.state.database).defaults(body)


@router.post('/authoring/preview')
def preview(body: AuthoringPreview, request: Request):
    return Authoring(request.app.state.database).preview(body)


@router.post('/authoring', status_code=201)
async def start(body: AuthoringStart, request: Request):
    result = Authoring(request.app.state.database).create(body)
    for job_id in result['job_ids']:
        request.app.state.authoring_runner.start(job_id)
    return result


@router.get('/authoring')
def history(request: Request, asset_id: str | None = None, offset: int = Query(default=0, ge=0)):
    return Authoring(request.app.state.database).list(asset_id, offset)


@router.get('/authoring/{run_id}')
def detail(run_id: str, request: Request):
    return Authoring(request.app.state.database).detail(run_id)


@router.get('/authoring-jobs/{job_id}/attempts')
def attempts(job_id: str, request: Request):
    return Authoring(request.app.state.database).attempts(job_id)


@router.post('/authoring-jobs/{job_id}/stop')
async def stop(job_id: str, request: Request):
    return request.app.state.authoring_runner.cancel(job_id)


@router.post('/authoring-jobs/{job_id}/retry')
async def retry(job_id: str, request: Request):
    return request.app.state.authoring_runner.retry(job_id)
