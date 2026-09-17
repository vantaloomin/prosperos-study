import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from server.database import encode
from server.workflow.models import ReviewPreview, ReviewStart, RoutingUpdate, SelectReview
from server.workflow.reviews import Reviews
from server.workflow.routing import Routing

router = APIRouter(prefix="/api")


@router.get("/stories/{story_id}/workflow")
def routing(story_id: str, request: Request):
    return Routing(request.app.state.database).detail(story_id)


@router.put("/stories/{story_id}/workflow")
def save_routing(story_id: str, body: RoutingUpdate, request: Request):
    return Routing(request.app.state.database).update(story_id, body)


@router.post("/branches/{branch_id}/reviews/preview")
def preview(branch_id: str, body: ReviewPreview, request: Request):
    return Reviews(request.app.state.database).preview(branch_id, body)


@router.post("/branches/{branch_id}/reviews", status_code=201)
async def create_review(branch_id: str, body: ReviewStart, request: Request):
    result = Reviews(request.app.state.database).create(branch_id, body)
    for job_id in result["job_ids"]:
        request.app.state.review_runner.start(job_id)
    return result


@router.get("/branches/{branch_id}/reviews")
def list_reviews(branch_id: str, request: Request, scene_id: str | None = None):
    return Reviews(request.app.state.database).list(branch_id, scene_id)


@router.get("/reviews/{run_id}")
def detail(run_id: str, request: Request):
    return Reviews(request.app.state.database).detail(run_id)


@router.put("/reviews/{run_id}/selection")
def select(run_id: str, body: SelectReview, request: Request):
    return Reviews(request.app.state.database).select(run_id, body.job_id)


async def review_updates(request, run_id):
    service = Reviews(request.app.state.database)
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


@router.get("/reviews/{run_id}/events")
async def events(run_id: str, request: Request):
    Reviews(request.app.state.database).detail(run_id)
    return StreamingResponse(review_updates(request, run_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/review-jobs/{job_id}/cancel")
async def cancel(job_id: str, request: Request):
    return request.app.state.review_runner.cancel(job_id)


@router.post("/review-jobs/{job_id}/retry")
async def retry(job_id: str, request: Request):
    return request.app.state.review_runner.retry(job_id)


@router.get("/review-jobs/{job_id}/attempts")
def attempts(job_id: str, request: Request):
    return Reviews(request.app.state.database).attempts(job_id)
