from fastapi import APIRouter, Request

from server.background.models import BackgroundUpdate, Preparation
from server.background.service import Background

router = APIRouter(prefix='/api')


@router.get('/branches/{branch_id}/background')
def context(branch_id: str, request: Request):
    return Background(request.app.state.database).context(branch_id)


@router.post('/branches/{branch_id}/background', status_code=201)
def prepare(branch_id: str, body: Preparation, request: Request):
    return Background(request.app.state.database).prepare(branch_id, body)


@router.put('/branches/{branch_id}/background')
def update(branch_id: str, body: BackgroundUpdate, request: Request):
    return Background(request.app.state.database).update(branch_id, body)


@router.get('/background/{background_id}/reveal')
def reveal(background_id: str, request: Request):
    return Background(request.app.state.database).reveal(background_id)
