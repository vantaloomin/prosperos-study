"""Local review and draft edits of Canon aids; never publish or alter prose."""
import json
from typing import Literal

from pydantic import ConfigDict, Field

from server.database import decode, one
from server.errors import require
from server.library_formats.sources import validate_new_markdown
from server.memory.canon_compiler import source_digest
from server.memory.canon_models import CanonCue, canon_policy
from server.models import Input

PAGE_SIZE = 12
SOURCE_PAGE = 2400


class CuePreview(Input):
    content: dict
    source_version_id: str | None = None
    query: str = Field(default='', max_length=2000)
    status: Literal['all', 'active', 'stale'] = 'all'
    offset: int = Field(default=0, ge=0)
    cue_id: str | None = None
    source_offset: int = Field(default=0, ge=0)


class CueFields(Input):
    model_config = ConfigDict(str_strip_whitespace=False, strict=True)
    summary: str = Field(max_length=32000)
    topics: list[str] = Field(max_length=256)
    aliases: list[str] = Field(max_length=256)


class CueChange(Input):
    content: dict
    expected_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    cue_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: Literal['edit', 'remove']
    fields: CueFields | None = None


def fingerprint(value):
    return source_digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def matching_source(text, cue):
    if cue.end <= len(text) and source_digest(text[cue.start:cue.end]) == cue.sha256:
        return text[cue.start:cue.end]
    return None


def published_source(connection, version_id):
    if not version_id:
        return None
    row = one(connection, 'SELECT * FROM asset_versions WHERE id=?', (version_id,))
    content = decode(row['content'])
    text = content.get('text', '')
    require(isinstance(text, str), 'This published version has no Markdown overview.')
    return {'text': text, 'number': row['number'], 'version_id': row['id']}


def source_page(cue, text, published, offset):
    original = matching_source(text, cue)
    origin, version = 'draft', None
    if original is None and published:
        original = matching_source(published['text'], cue)
        origin, version = 'published', published['number']
    if original is None:
        return None
    offset = min(offset, max(0, (len(original) - 1) // SOURCE_PAGE * SOURCE_PAGE))
    end = min(len(original), offset + SOURCE_PAGE)
    return {'origin': origin, 'version': version, 'text': original[offset:end],
            'offset': offset, 'end': end, 'length': len(original),
            'next_offset': end if end < len(original) else None}


def cue_row(cue, number, text):
    data = cue.model_dump()
    return {'id': fingerprint(data), 'number': number, 'cue': data,
            'status': 'active' if matching_source(text, cue) is not None else 'stale'}


def includes_query(row, query):
    cue = row['cue']
    searchable = '\n'.join([cue['summary'], *cue['topics'], *cue['aliases']]).casefold()
    return query.casefold() in searchable


def preview_cues(connection, body):
    validate_new_markdown(body.content)
    policy = canon_policy(body.content)
    text = body.content.get('text', '')
    published = published_source(connection, body.source_version_id)
    rows = [cue_row(cue, index + 1, text) for index, cue in enumerate(policy.cues)]
    active = sum(row['status'] == 'active' for row in rows)
    selected = [row for row in rows if (body.status == 'all' or row['status'] == body.status)
                and includes_query(row, body.query)]
    if body.cue_id:
        selected = [row for row in rows if row['id'] == body.cue_id]
        require(bool(selected), 'This search aid changed. Reopen it from the current draft.', 409)
    offset = min(body.offset, max(0, (len(selected) - 1) // PAGE_SIZE * PAGE_SIZE))
    items = selected[offset:offset + PAGE_SIZE]
    for row in items:
        row['source'] = source_page(CanonCue.model_validate(row['cue']), text, published, body.source_offset)
    return {'fingerprint': fingerprint(body.content), 'total': len(rows), 'active': active,
            'stale': len(rows) - active, 'matches': len(selected), 'offset': offset, 'items': items,
            'next_offset': offset + PAGE_SIZE if offset + PAGE_SIZE < len(selected) else None}


def change_cue(body):
    validate_new_markdown(body.content)
    require(fingerprint(body.content) == body.expected_fingerprint,
            'This Canon draft changed. Reopen the aid before applying your edit.', 409)
    policy = canon_policy(body.content)
    cues = [cue.model_dump() for cue in policy.cues]
    index = next((index for index, cue in enumerate(cues) if fingerprint(cue) == body.cue_id), None)
    require(index is not None, 'This search aid changed or was removed. Reopen the current draft.', 409)
    if body.action == 'remove':
        require(body.fields is None, 'Removing an aid does not accept replacement fields.')
        cues.pop(index)
    else:
        require(body.fields is not None, 'Enter the edited search-aid fields.')
        cues[index] = cues[index] | body.fields.model_dump()
    updated = policy.model_dump() | {'cues': cues}
    canon_policy({'canon_recall': updated})
    return {'canon_recall': updated}
