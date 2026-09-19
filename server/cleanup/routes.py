from fastapi import APIRouter, Request

from server.cleanup.models import CleanupSelection, CleanupSetting
from server.cleanup.settings import settings, update
from server.cleanup.storage import select

router = APIRouter(prefix='/api')


@router.get('/branches/{branch_id}/cleanup')
def get_setting(branch_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return settings(connection, branch_id)


@router.put('/branches/{branch_id}/cleanup')
async def set_setting(branch_id: str, body: CleanupSetting, request: Request):
    result = update(request.app.state.database, branch_id, body)
    request.app.state.runner.cancel_cleanup(branch_id)
    return result


@router.post('/candidates/{candidate_id}/cleanup-selection')
def choose_wording(candidate_id: str, body: CleanupSelection, request: Request):
    return select(request.app.state.database, candidate_id, body)
