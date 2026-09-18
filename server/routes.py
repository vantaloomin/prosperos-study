from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from server.adoptions import Adoptions
from server.assessment.preparation import after_acceptance
from server.branch_timing import BranchTimings
from server.branches import Branches
from server.library import Library
from server.models import (
    AdoptionApply,
    AdoptionPreviewRequest,
    AssetCreate,
    AssetPublish,
    AttachmentUpdate,
    ForkCreate,
    MessageCreate,
    PassageRevision,
    StoryCreate,
    StoryUpdate,
    VersionLookup,
)
from server.operations import receipt
from server.passage_revisions import revise_passage
from server.stories import Stories

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "application": "Roleplay", "storage": "SQLite"}


@router.get('/operations/{operation_id}')
def operation_receipt(operation_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return receipt(connection, operation_id)


@router.get("/stories")
def stories(request: Request):
    return Stories(request.app.state.database).list()


@router.post("/stories", status_code=201)
def create_story(body: StoryCreate, request: Request):
    return Stories(request.app.state.database).create(body)


@router.get("/stories/{story_id}")
def get_story(story_id: str, request: Request):
    return Stories(request.app.state.database).detail(story_id)


@router.put("/stories/{story_id}")
def update_story(story_id: str, body: StoryUpdate, request: Request):
    return Stories(request.app.state.database).update(story_id, body)


@router.put("/stories/{story_id}/attachments")
def update_attachments(story_id: str, body: AttachmentUpdate, request: Request):
    return Stories(request.app.state.database).attachments(story_id, body)


@router.get("/branches/{branch_id}", response_class=JSONResponse)
def get_branch(branch_id: str, request: Request):
    timing = BranchTimings()
    # Stored branch data already contains only JSON types. Avoid a second tree walk.
    response = JSONResponse(Branches(request.app.state.database).detail(branch_id, timing))
    timing.mark("serialize")
    response.headers["Server-Timing"] = timing.header()
    return response


@router.post("/branches/{branch_id}/messages", status_code=201)
async def create_message(branch_id: str, body: MessageCreate, request: Request):
    result = await run_in_threadpool(Branches(request.app.state.database).append, branch_id, body)
    return await after_acceptance(request, result)


@router.post("/branches/{branch_id}/forks", status_code=201)
def create_fork(branch_id: str, body: ForkCreate, request: Request):
    return Branches(request.app.state.database).fork(branch_id, body)


@router.post('/branches/{branch_id}/passage-revisions', status_code=201)
def create_passage_revision(branch_id: str, body: PassageRevision, request: Request):
    return revise_passage(request.app.state.database, branch_id, body)


@router.get("/library")
def library(request: Request):
    return Library(request.app.state.database).list()


@router.post("/library", status_code=201)
def create_asset(body: AssetCreate, request: Request):
    return Library(request.app.state.database).create(body)


@router.get("/library/{asset_id}/versions")
def asset_versions(asset_id: str, request: Request):
    return Library(request.app.state.database).history(asset_id)


@router.post("/library/{asset_id}/versions", status_code=201)
def publish_asset(asset_id: str, body: AssetPublish, request: Request):
    return Library(request.app.state.database).publish(asset_id, body)


@router.post('/library/versions/lookup')
def lookup_versions(body: VersionLookup, request: Request):
    return Library(request.app.state.database).references(body.version_ids)


@router.get("/versions/{version_id}/adoption")
def preview_adoption(version_id: str, request: Request):
    return Adoptions(request.app.state.database).preview(version_id)


@router.post("/versions/{version_id}/adoption")
def apply_adoption(version_id: str, body: AdoptionApply, request: Request):
    return Adoptions(request.app.state.database).apply(version_id, body)


@router.post("/versions/{version_id}/adoption/preview")
def preview_linked_adoption(version_id: str, body: AdoptionPreviewRequest, request: Request):
    return Adoptions(request.app.state.database).preview(version_id, body.additional_version_ids)
