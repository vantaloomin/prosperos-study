from fastapi import APIRouter, Request
from pydantic import Field

from server.authoring.models import AuthoringPreview
from server.authoring.service import Authoring
from server.database import decode, one
from server.errors import require
from server.library_formats.sources import validate_new_markdown
from server.memory.enrichment import (
    ENRICHMENT_KEY,
    EnrichmentCue,
    apply_enrichment,
    enrichment_inputs,
)
from server.models import Input

router = APIRouter(prefix='/api/canon')


class EnrichmentPreview(Input):
    name: str = Field(max_length=120)
    content: dict
    selected: list[str] = Field(min_length=1, max_length=8)
    draft_id: str = Field(min_length=1, max_length=100)
    source_version_id: str | None = None
    direction: str = Field(default='', max_length=10000)
    profile_ids: list[str] = Field(default_factory=list, max_length=4)


class EnrichmentApply(Input):
    job_id: str
    content: dict
    cues: list[EnrichmentCue] = Field(min_length=1, max_length=8)


@router.post('/enrichment-preview')
def preview(body: EnrichmentPreview, request: Request):
    validate_new_markdown(body.content)
    inputs = enrichment_inputs(body.name, body.content, body.selected)
    authoring = AuthoringPreview(source_version_id=body.source_version_id, draft_id=body.draft_id,
        kind='lorebook', name=body.name, target_key='canon-cues', target_label='Canon search aids',
        step=ENRICHMENT_KEY, direction=body.direction, profile_ids=body.profile_ids, **inputs)
    return {'request': authoring.model_dump(), **Authoring(request.app.state.database).preview(authoring)}


@router.post('/enrichment-apply')
def apply(body: EnrichmentApply, request: Request):
    validate_new_markdown(body.content)
    with request.app.state.database.connect() as connection:
        job = one(connection, 'SELECT * FROM authoring_jobs WHERE id=?', (body.job_id,))
        require(job['step'] == ENRICHMENT_KEY and job['status'] == 'done', 'Choose a completed Canon enrichment request.', 409)
        return apply_enrichment(body.content, decode(job['snapshot']), decode(job['result'])['enrichment'], body.cues)
