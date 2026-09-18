"""On-demand compilation previews and reviewed exports; no narrative writes."""
from fastapi import APIRouter, Request
from pydantic import Field

from server.errors import require
from server.library_formats.sources import validate_new_markdown
from server.memory.canon_compiler import CueIndex, compile_overview
from server.memory.canon_curation import CueChange, CuePreview, change_cue, preview_cues
from server.memory.canon_export import PackExport, export_pack
from server.memory.retrieval import Corpus
from server.models import Input

router = APIRouter(prefix='/api')


class CompilePreview(Input):
    name: str = Field(default='Canon', max_length=120)
    content: dict
    query: str = Field(default='', max_length=4000)
    offset: int = Field(default=0, ge=0)


@router.post('/canon/compile-preview')
def compile_preview(body: CompilePreview):
    validate_new_markdown(body.content)
    chunks, report = compile_overview('draft', body.name, body.content)
    hits = Corpus(chunks).search(body.query, limit=16, cosine_only=True) if body.query else []
    selected = [hit.chunk for hit in hits] if body.query else chunks
    cues = CueIndex(body.content)
    require(body.offset <= len(selected), 'This page is outside the compiled Canon.')
    return {**report, 'matches': len(selected), 'offset': body.offset,
            'items': [{**chunk.evidence(), 'search_cues': cues.fields(chunk)}
                      for chunk in selected[body.offset:body.offset + 12]],
            'next_offset': body.offset + 12 if body.offset + 12 < len(selected) else None}


@router.post('/versions/{version_id}/brain-pack')
def brain_pack(version_id: str, body: PackExport, request: Request):
    return export_pack(request.app.state.database, version_id, body)


@router.post('/canon/cues-preview')
def cues_preview(body: CuePreview, request: Request):
    with request.app.state.database.connect() as connection:
        return preview_cues(connection, body)


@router.post('/canon/cues-change')
def cues_change(body: CueChange):
    return change_cue(body)
