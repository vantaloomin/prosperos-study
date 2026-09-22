from fastapi import APIRouter, Query, Request

from server.inspiration.draws import Draws
from server.inspiration.models import DeckCreate, DeckPublish, Draw, Preview
from server.inspiration.resources import Decks
from server.inspiration.selection import preview
from server.writing.models import ResourceArchive

router = APIRouter(prefix='/api/inspiration', tags=['inspiration'])


@router.get('/decks')
def catalog(request: Request, include_archived: bool = False):
    return Decks(request.app.state.database).list(include_archived)


@router.post('/decks', status_code=201)
def create(body: DeckCreate, request: Request):
    return Decks(request.app.state.database).create(body)


@router.get('/decks/{deck_id}/versions')
def history(deck_id: str, request: Request):
    return Decks(request.app.state.database).history(deck_id)


@router.post('/decks/{deck_id}/versions', status_code=201)
def publish(deck_id: str, body: DeckPublish, request: Request):
    return Decks(request.app.state.database).publish(deck_id, body)


@router.put('/decks/{deck_id}/archived')
def archive(deck_id: str, body: ResourceArchive, request: Request):
    return Decks(request.app.state.database).archive(deck_id, body)


@router.get('/versions/{version_id}')
def read_version(version_id: str, request: Request):
    return Decks(request.app.state.database).version(version_id)


@router.post('/preview')
def preview_deck(body: Preview):
    return preview(body)


@router.post('/versions/{version_id}/draws', status_code=201)
def draw(version_id: str, body: Draw, request: Request):
    return Draws(request.app.state.database).create(version_id, body)


@router.get('/draws')
def draws(request: Request, version_id: str | None = None, branch_id: str | None = None, offset: int = Query(default=0, ge=0, le=1_000_000)):
    return Draws(request.app.state.database).history(version_id, branch_id, offset)


@router.get('/draws/{draw_id}')
def draw_receipt(draw_id: str, request: Request):
    return Draws(request.app.state.database).view(draw_id)
