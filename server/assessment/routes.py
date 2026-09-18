from fastapi import APIRouter, Request

from server.assessment.models import AssessmentDecision
from server.assessment.service import Assessments

router = APIRouter(prefix='/api')


@router.get('/branches/{branch_id}/assessments')
def list_assessments(branch_id: str, request: Request):
    return Assessments(request.app.state.database).list(branch_id)


@router.get('/assessments/{run_id}')
def detail(run_id: str, request: Request):
    return Assessments(request.app.state.database).detail(run_id)


@router.post('/assessments/{run_id}/decision')
async def decide(run_id: str, body: AssessmentDecision, request: Request):
    service = Assessments(request.app.state.database)
    result = service.decide(run_id, body)
    if 'id' not in result:
        return result
    for job in service.stop(run_id):
        request.app.state.assessment_runner.cancel(job['id'])
    for candidate in request.app.state.runner.pending(result['id']):
        request.app.state.runner.start(candidate['id'])
    return result


@router.post('/assessments/{run_id}/stop')
async def stop(run_id: str, request: Request):
    for job in Assessments(request.app.state.database).stop(run_id):
        request.app.state.assessment_runner.cancel(job['id'])
    return {'stopped': True}


@router.post('/assessment-jobs/{job_id}/retry')
async def retry(job_id: str, request: Request):
    return request.app.state.assessment_runner.retry(job_id)


@router.get('/assessment-jobs/{job_id}/attempts')
def attempts(job_id: str, request: Request):
    return Assessments(request.app.state.database).attempts(job_id)
