import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from server.assessment.service import Assessments
from server.assessment.writing import WritingRequests
from server.context_inspector import ContextInspector, ContextSectionRequest
from server.database import encode
from server.generation_models import (
    AcceptCandidate,
    AlternateRequest,
    ContextPreviewRequest,
    GenerateRequest,
)
from server.generations import Generations
from server.prompts import PromptActivation, Prompts, PromptSectionActivation, PromptUpdate

router = APIRouter(prefix="/api")


@router.post('/branches/{branch_id}/context-preview')
def context_preview(branch_id: str, body: ContextPreviewRequest, request: Request):
    return ContextInspector(request.app.state.database).preview(branch_id, body)


@router.post('/branches/{branch_id}/context-preview/section')
def context_section(branch_id: str, body: ContextSectionRequest, request: Request):
    return ContextInspector(request.app.state.database).section(branch_id, body)


@router.post("/branches/{branch_id}/generations", status_code=201)
async def generate(branch_id: str, body: GenerateRequest, request: Request):
    result = await run_in_threadpool(WritingRequests(request.app.state.database).create, branch_id, body)
    if 'assessment_id' in result:
        for job in Assessments(request.app.state.database).pending(result['assessment_id']):
            request.app.state.assessment_runner.start(job['id'])
        return result
    runner = request.app.state.runner
    request.app.state.assessment_runner.stop_superseded(branch_id)
    for candidate in runner.pending(result["id"]):
        runner.start(candidate["id"])
    return result


@router.get("/branches/{branch_id}/generations")
def list_generations(branch_id: str, request: Request):
    return Generations(request.app.state.database).list(branch_id)


@router.get("/generations/{generation_id}")
def generation_detail(generation_id: str, request: Request):
    return Generations(request.app.state.database).detail(generation_id)


async def updates(request, generation_id):
    service = Generations(request.app.state.database)
    previous = ""
    while not await request.is_disconnected():
        result = service.detail(generation_id)
        data = encode({"candidates": result["candidates"], "stale": result["stale"]})
        if data != previous:
            yield f"data: {data}\n\n"
            previous = data
        if all(c["status"] not in {"queued", "running"} for c in result["candidates"]):
            return
        await asyncio.sleep(0.25)


@router.get("/generations/{generation_id}/events")
async def generation_events(generation_id: str, request: Request):
    Generations(request.app.state.database).detail(generation_id)
    return StreamingResponse(updates(request, generation_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/candidates/{candidate_id}/accept")
def accept(candidate_id: str, body: AcceptCandidate, request: Request):
    return Generations(request.app.state.database).accept(candidate_id, body)


@router.post("/candidates/{candidate_id}/alternatives", status_code=201)
async def alternate(candidate_id: str, body: AlternateRequest, request: Request):
    result = Generations(request.app.state.database).alternate(candidate_id, body)
    request.app.state.runner.start(result["candidate_id"])
    return result


@router.get("/candidates/{candidate_id}/attempts")
def attempts(candidate_id: str, request: Request):
    return Generations(request.app.state.database).attempts(candidate_id)


@router.post("/candidates/{candidate_id}/cancel")
async def cancel(candidate_id: str, request: Request):
    return request.app.state.runner.cancel(candidate_id)


@router.post("/candidates/{candidate_id}/retry")
async def retry(candidate_id: str, request: Request):
    return request.app.state.runner.retry(candidate_id)


@router.get("/prompts")
def prompts(request: Request, story_id: str | None = None):
    return Prompts(request.app.state.database).list(story_id)


@router.put('/prompt-sections/activation')
def activate_prompt_section(body: PromptSectionActivation, request: Request):
    return Prompts(request.app.state.database).activate_section(body)


@router.put("/prompts/{key}")
def update_prompt(key: str, body: PromptUpdate, request: Request, story_id: str | None = None):
    return Prompts(request.app.state.database).update(key, body, story_id)


@router.put('/prompts/{key}/activation')
def activate_prompt(key: str, body: PromptActivation, request: Request):
    return Prompts(request.app.state.database).activate(key, body)


@router.get("/prompts/{key}/versions")
def prompt_history(key: str, request: Request):
    return Prompts(request.app.state.database).history(key)
