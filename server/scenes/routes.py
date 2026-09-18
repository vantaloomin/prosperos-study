import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from server.assessment.preparation import after_acceptance
from server.continuity import continuity_view
from server.database import encode, one
from server.memory.plan_state import plan_head
from server.scenes.actor_context import actor_choices
from server.scenes.continuity_models import SceneAcceptance
from server.scenes.models import (
    SceneApproval,
    SceneChoice,
    SceneCreate,
    SceneEdit,
    SceneStart,
    SceneStep,
)
from server.scenes.revision_models import RevisionApproval, TriageEdit
from server.scenes.service import Scenes
from server.scenes.state import run_record

router = APIRouter(prefix="/api")


@router.post("/branches/{branch_id}/scenes", status_code=201)
def create(branch_id: str, body: SceneCreate, request: Request):
    return Scenes(request.app.state.database).create(branch_id, body)


@router.get("/branches/{branch_id}/scenes")
def history(branch_id: str, request: Request):
    return Scenes(request.app.state.database).list(branch_id)


@router.get("/scenes/{run_id}")
def detail(run_id: str, request: Request):
    return Scenes(request.app.state.database).detail(run_id)


@router.post("/scenes/{run_id}/preview")
def preview(run_id: str, body: SceneStep, request: Request):
    return Scenes(request.app.state.database).preview(run_id, body)


@router.get('/scenes/{run_id}/character-evidence')
def character_evidence(run_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return actor_choices(connection, run_record(connection, run_id))


@router.get('/scenes/{run_id}/reports')
def reports(run_id: str, request: Request):
    return Scenes(request.app.state.database).reports(run_id)


@router.post("/scenes/{run_id}/stages", status_code=201)
async def start(run_id: str, body: SceneStart, request: Request):
    result = Scenes(request.app.state.database).start(run_id, body)
    for job_id in result["job_ids"]:
        request.app.state.scene_runner.start(job_id)
    return result


@router.post("/scenes/{run_id}/choose")
def choose(run_id: str, body: SceneChoice, request: Request):
    return Scenes(request.app.state.database).decide(run_id, body, "choose")


@router.post("/scenes/{run_id}/edit")
def edit(run_id: str, body: SceneEdit, request: Request):
    return Scenes(request.app.state.database).decide(run_id, body, "edit")


@router.post("/scenes/{run_id}/approve")
def approve(run_id: str, body: SceneApproval, request: Request):
    return Scenes(request.app.state.database).decide(run_id, body, "approve")


@router.post('/scenes/{run_id}/resolve')
def resolve(run_id: str, body: TriageEdit, request: Request):
    return Scenes(request.app.state.database).decide(run_id, body, 'resolve')


@router.post('/scenes/{run_id}/approve-revision')
def approve_package(run_id: str, body: RevisionApproval, request: Request):
    return Scenes(request.app.state.database).decide(run_id, body, 'approve-revision')


@router.post('/scenes/{run_id}/repair-patch')
def repair(run_id: str, body: SceneApproval, request: Request):
    return Scenes(request.app.state.database).decide(run_id, body, 'repair-patch')


@router.post('/scenes/{run_id}/accept')
async def accept(run_id: str, body: SceneAcceptance, request: Request):
    result = await run_in_threadpool(Scenes(request.app.state.database).decide, run_id, body, 'accept')
    return await after_acceptance(request, result)


@router.get('/branches/{branch_id}/continuity')
def continuity(branch_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT head_id FROM branches WHERE id=?', (branch_id,))
        return continuity_view(connection, branch['head_id'], plan_head(connection, branch_id))


async def updates(request, run_id):
    service = Scenes(request.app.state.database)
    previous = ""
    while not await request.is_disconnected():
        result = service.detail(run_id)
        data = encode(result)
        if data != previous:
            yield f"data: {data}\n\n"
            previous = data
        if all(job["status"] not in {"queued", "running"} for job in result["jobs"]):
            return
        await asyncio.sleep(0.25)


@router.get("/scenes/{run_id}/events")
async def events(run_id: str, request: Request):
    Scenes(request.app.state.database).detail(run_id)
    return StreamingResponse(updates(request, run_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/scene-jobs/{job_id}/cancel")
async def cancel(job_id: str, request: Request):
    return request.app.state.scene_runner.cancel(job_id)


@router.post("/scene-jobs/{job_id}/retry")
async def retry(job_id: str, request: Request):
    return request.app.state.scene_runner.retry(job_id)


@router.get("/scene-jobs/{job_id}/attempts")
def attempts(job_id: str, request: Request):
    return Scenes(request.app.state.database).attempts(job_id)
