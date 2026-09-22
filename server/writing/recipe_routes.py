from fastapi import APIRouter, Request

from server.writing.recipe_models import RecipeJobCommand, RecipeRunCreate, RecipeStepStart
from server.writing.recipe_service import RecipeRuns

router = APIRouter(prefix='/api')


@router.post('/branches/{branch_id}/recipe-runs', status_code=201)
def create(branch_id: str, body: RecipeRunCreate, request: Request):
    return RecipeRuns(request.app.state.database).create(branch_id, body)


@router.get('/branches/{branch_id}/recipe-runs')
def list_runs(branch_id: str, request: Request):
    return RecipeRuns(request.app.state.database).list(branch_id)


@router.get('/recipe-runs/operations/{operation_id}')
def operation(operation_id: str, request: Request):
    return RecipeRuns(request.app.state.database).operation(operation_id)


@router.get('/recipe-runs/{run_id}')
def detail(run_id: str, request: Request):
    return RecipeRuns(request.app.state.database).detail(run_id)


@router.post('/recipe-runs/{run_id}/preview-step')
def preview_step(run_id: str, request: Request):
    return RecipeRuns(request.app.state.database).preview_step(run_id)


@router.post('/recipe-runs/{run_id}/steps', status_code=201)
async def start_step(run_id: str, body: RecipeStepStart, request: Request):
    result = RecipeRuns(request.app.state.database).start_step(run_id, body)
    for job_id in result['job_ids']:
        request.app.state.recipe_runner.start(job_id)
    return result


@router.post('/recipe-jobs/{job_id}/stop')
async def stop(job_id: str, request: Request, body: RecipeJobCommand | None = None):
    return request.app.state.recipe_runner.cancel(job_id, body.expected_attempt if body else None)


@router.post('/recipe-jobs/{job_id}/retry')
async def retry(job_id: str, request: Request, body: RecipeJobCommand | None = None):
    return request.app.state.recipe_runner.retry(job_id, body.expected_attempt if body else None)


@router.get('/recipe-jobs/{job_id}/attempts')
def attempts(job_id: str, request: Request):
    return RecipeRuns(request.app.state.database).attempts(job_id)
