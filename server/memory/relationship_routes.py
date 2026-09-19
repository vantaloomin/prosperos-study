from fastapi import APIRouter, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from server.database import one
from server.memory.relationship_context import plan_requests
from server.memory.relationship_sources import active_annotations, source_catalog
from server.memory.relationship_storage import create_jobs, job_detail, recent_jobs
from server.models import Input

router = APIRouter(prefix='/api')


class PrepareRelationships(Input):
    expected_revision: int = Field(ge=0)
    operation_id: str = Field(min_length=8, max_length=100)


def relationship_status(database, provider, branch_id):
    with database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        sources, _ = source_catalog(connection, branch)
        aids = active_annotations(connection, branch, sources)
        from server.errors import DomainError
        try:
            plan = plan_requests(connection, branch_id)
            from server.memory.relationship_sources import story_policy
            from server.profiles import resolve_profile
            story, _ = story_policy(connection, branch)
            capability = provider.background_capability(resolve_profile(connection, story, 'writer'))
            return {'eligible': plan['eligible'], 'prepared': plan['prepared'], 'annotations': len(aids),
                    'available': True, 'background': capability, 'reason': ''}
        except DomainError as error:
            return {'eligible': len(sources), 'prepared': 0, 'annotations': len(aids),
                    'available': False, 'background': None, 'reason': error.message}


@router.get('/branches/{branch_id}/relationships')
def status(branch_id: str, request: Request):
    database = request.app.state.database
    return {**relationship_status(database, request.app.state.relationship_runner.provider, branch_id),
            'jobs': recent_jobs(database, branch_id)}


@router.post('/branches/{branch_id}/relationships', status_code=201)
async def prepare(branch_id: str, body: PrepareRelationships, request: Request):
    result = await run_in_threadpool(create_jobs, request.app.state.database, branch_id, body)
    for identity in result['job_ids']:
        request.app.state.relationship_runner.start_job(identity)
    return result


@router.get('/relationship-jobs/{identity}')
def detail(identity: str, request: Request):
    return job_detail(request.app.state.database, identity)


@router.post('/relationship-jobs/{identity}/cancel')
async def cancel(identity: str, request: Request):
    return request.app.state.relationship_runner.cancel(identity)


@router.post('/relationship-jobs/{identity}/retry')
async def retry(identity: str, request: Request):
    return request.app.state.relationship_runner.retry(identity)
