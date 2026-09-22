from fastapi import APIRouter, Query, Request

from server.branch_tools.comparisons import create_comparison, list_comparisons, read_comparison
from server.branch_tools.curation import update_curation
from server.branch_tools.models import BranchSearch, ComparisonCreate, CurationUpdate
from server.branch_tools.search import branch_search

router = APIRouter(prefix='/api')


@router.put('/branches/{branch_id}/curation')
def curate(branch_id: str, body: CurationUpdate, request: Request):
    return update_curation(request.app.state.database, branch_id, body)


@router.post('/stories/{story_id}/branch-comparisons', status_code=201)
def compare(story_id: str, body: ComparisonCreate, request: Request):
    return create_comparison(request.app.state.database, story_id, body)


@router.get('/stories/{story_id}/branch-comparisons')
def comparisons(story_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return list_comparisons(connection, story_id)


@router.get('/branch-comparisons/{comparison_id}')
def comparison(comparison_id: str, request: Request, offset: int = Query(0, ge=0),
               limit: int = Query(20, ge=1, le=40), differences_only: bool = False):
    with request.app.state.database.connect() as connection:
        return read_comparison(connection, comparison_id, offset, limit, differences_only)


@router.post('/stories/{story_id}/branch-search')
def search(story_id: str, body: BranchSearch, request: Request):
    with request.app.state.database.connect() as connection:
        return branch_search(connection, story_id, body)
