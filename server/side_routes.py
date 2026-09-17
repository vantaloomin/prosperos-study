from fastapi import APIRouter, Request

from server.side_conversations import SideConversations, SideQuestion, SideThreadCreate

router = APIRouter(prefix="/api")


@router.get("/stories/{story_id}/side-conversations")
def threads(story_id: str, request: Request):
    return SideConversations(request.app.state.database).threads(story_id)


@router.post("/stories/{story_id}/side-conversations", status_code=201)
def create(story_id: str, body: SideThreadCreate, request: Request):
    return SideConversations(request.app.state.database).create_thread(story_id, body.name)


@router.get("/side-conversations/{thread_id}")
def detail(thread_id: str, request: Request):
    return SideConversations(request.app.state.database).detail(thread_id)


@router.post("/side-conversations/{thread_id}/questions", status_code=201)
async def ask(thread_id: str, body: SideQuestion, request: Request):
    result = SideConversations(request.app.state.database).ask(thread_id, body)
    runner = request.app.state.side_runner
    for reply in runner.pending(result["id"]):
        runner.start(reply["id"])
    return result


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
