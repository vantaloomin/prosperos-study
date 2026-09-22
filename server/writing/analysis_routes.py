from fastapi import APIRouter, Request

from server.writing.analysis_models import AnalysisPreview, AnalysisStart
from server.writing.analysis_service import StyleAnalyses

router = APIRouter(prefix='/api/writing-analyses')


@router.post('/preview')
def preview(body: AnalysisPreview, request: Request):
    return StyleAnalyses(request.app.state.database).preview(body)


@router.post('', status_code=201)
async def start(body: AnalysisStart, request: Request):
    result = StyleAnalyses(request.app.state.database).create(body)
    request.app.state.style_analysis_runner.start(result['id'])
    return result


@router.get('')
def list_analyses(request: Request, source_version_id: str | None = None, draft_id: str | None = None):
    return StyleAnalyses(request.app.state.database).list(source_version_id, draft_id)


@router.get('/operations/{operation_id}')
def operation(operation_id: str, request: Request):
    return StyleAnalyses(request.app.state.database).operation(operation_id)


@router.get('/{job_id}')
def detail(job_id: str, request: Request):
    return StyleAnalyses(request.app.state.database).detail(job_id)


@router.get('/{job_id}/attempts')
def attempts(job_id: str, request: Request):
    return StyleAnalyses(request.app.state.database).attempts(job_id)


@router.post('/{job_id}/stop')
async def stop(job_id: str, request: Request):
    return request.app.state.style_analysis_runner.cancel(job_id)


@router.post('/{job_id}/retry')
async def retry(job_id: str, request: Request):
    return request.app.state.style_analysis_runner.retry(job_id)
