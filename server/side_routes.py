from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from server.side_conversations import SideConversations, SideQuestion, SideThreadCreate
from server.side_drafts import SideDraftSave, read_draft, save_draft
from server.side_organization import SideThreadUpdate, search_threads, update_thread
from server.side_targets import (
    ContextCreate,
    ContextDecision,
    context_head,
    follow_context,
    select_context,
)

router = APIRouter(prefix="/api")


@router.get('/side-conversations/{thread_id}/context')
def selected_context(thread_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return context_head(connection, thread_id)


@router.post('/side-conversations/{thread_id}/context', status_code=201)
def pin_context(thread_id: str, body: ContextCreate, request: Request):
    return select_context(request.app.state.database, thread_id, body)


@router.post('/side-conversations/{thread_id}/context/follow')
def clear_context(thread_id: str, body: ContextDecision, request: Request):
    return follow_context(request.app.state.database, thread_id, body)


@router.get('/side-conversations/{thread_id}/draft')
def draft(thread_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return read_draft(connection, thread_id)


@router.put('/side-conversations/{thread_id}/draft')
def update_draft(thread_id: str, body: SideDraftSave, request: Request):
    return save_draft(request.app.state.database, thread_id, body)


@router.get("/stories/{story_id}/side-conversations")
def threads(story_id: str, request: Request, include_archived: bool = False):
    return SideConversations(request.app.state.database).threads(story_id, include_archived)


@router.get('/stories/{story_id}/side-conversations/search')
def search_conversations(story_id: str, request: Request, query: str = Query('', max_length=200),
                         include_archived: bool = False, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    with request.app.state.database.connect() as connection:
        return search_threads(connection, story_id, query.strip(), include_archived, offset, limit)


@router.put('/side-conversations/{thread_id}/organization')
def organize(thread_id: str, body: SideThreadUpdate, request: Request):
    return update_thread(request.app.state.database, thread_id, body)


@router.post("/stories/{story_id}/side-conversations", status_code=201)
def create(story_id: str, body: SideThreadCreate, request: Request):
    return SideConversations(request.app.state.database).create_thread(story_id, body.name)


@router.get("/side-conversations/{thread_id}")
def detail(thread_id: str, request: Request):
    return SideConversations(request.app.state.database).detail(thread_id)


@router.post("/side-conversations/{thread_id}/questions", status_code=201)
async def ask(thread_id: str, body: SideQuestion, request: Request):
    result = await run_in_threadpool(SideConversations(request.app.state.database).ask, thread_id, body)
    runner = request.app.state.side_runner
    for reply in runner.pending(result["id"]):
        runner.start(reply["id"])
    return result


@router.post('/side-conversations/{thread_id}/preview')
def preview(thread_id: str, body: SideQuestion, request: Request):
    return SideConversations(request.app.state.database).preview(thread_id, body)


@router.get("/side-turns/{turn_id}/sources")
def sources(turn_id: str, request: Request):
    return SideConversations(request.app.state.database).sources(turn_id)


@router.post("/side-replies/{reply_id}/select")
def select(reply_id: str, request: Request):
    return SideConversations(request.app.state.database).select(reply_id)


@router.post("/side-replies/{reply_id}/cancel")
async def cancel(reply_id: str, request: Request):
    return request.app.state.side_runner.cancel(reply_id)


@router.post("/side-replies/{reply_id}/retry", status_code=201)
async def retry(reply_id: str, request: Request):
    return request.app.state.side_runner.retry(reply_id)


@router.get("/side-turns/{turn_id}/source-search")
def search_sources(turn_id: str, request: Request, query: str = Query(default="", max_length=1000),
                   offset: int = Query(default=0, ge=0, le=1000000)):
    return SideConversations(request.app.state.database).search_sources(turn_id, query, offset)


@router.get("/side-turns/{turn_id}/source")
def read_source(turn_id: str, request: Request, source_id: str = Query(max_length=500),
                offset: int = Query(default=0, ge=0), length: int = Query(default=2400, ge=1, le=2400)):
    return SideConversations(request.app.state.database).read_source(turn_id, source_id, offset, length)


@router.get("/side-replies/{reply_id}/requests/{index}")
def request_inputs(reply_id: str, index: int, request: Request):
    return SideConversations(request.app.state.database).request_inputs(reply_id, index)
