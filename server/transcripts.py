"""Readable exports contain accepted text, never private context or run payloads."""

import hashlib
import html
import re
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response

from server.branches import path_nodes
from server.database import decode, identifier, many, now, one
from server.errors import require
from server.models import Input
from server.stories import check_revision

router = APIRouter(prefix="/api")
ROLE_LABELS = {"user": "You", "assistant": "Narration", "narrator": "Narration", "ooc": "Out of character"}
WRITING_LABELS = {"user": "Character contribution", "assistant": "Story text", "narrator": "Story text", "ooc": "Author note"}


class TranscriptOptions(Input):
    expected_revision: int
    from_node_id: str | None = None
    through_node_id: str | None = None
    include_ooc: bool = False
    include_timestamps: bool = False
    include_models: bool = False


def markdown_text(value):
    """Keep literal chat text literal in Markdown, including embedded HTML."""
    escaped = re.sub(r"([\\`*_\[\]#|~])", r"\\\1", html.escape(str(value), quote=False))
    escaped = re.sub(r"(?m)^(\s*)([-+])(?=\s)", r"\1\\\2", escaped)
    return re.sub(r"(?m)^(\s*\d+)([.)])(?=\s)", r"\1\\\2", escaped)


def selected_passage(messages, options):
    indices = {message["id"]: index for index, message in enumerate(messages)}
    for node_id in (options.from_node_id, options.through_node_id):
        require(node_id is None or node_id in indices, "Choose a passage on this branch.", 409)
    start = indices[options.from_node_id] if options.from_node_id else 0
    end = indices[options.through_node_id] + 1 if options.through_node_id else len(messages)
    require(start <= end - 1 or not messages, "The passage must end at or after its start.")
    return messages[start:end]


def model_labels(connection, messages):
    ids = list({message["metadata"].get("candidate_id") for message in messages} - {None})
    labels = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows = many(connection, f"SELECT id,profile FROM candidates WHERE id IN ({placeholders})", chunk)
        labels.update({row["id"]: decode(row["profile"])["config"]["model"] for row in rows})
    return labels


def message_markdown(message, options, labels, roles):
    heading = roles[message["role"]]
    metadata = []
    if options.include_timestamps:
        metadata.append(message["created_at"])
    model = labels.get(message["metadata"].get("candidate_id"))
    if options.include_models and model:
        metadata.append(f"Model: {model}")
    suffix = f"\n\n{markdown_text(' · '.join(metadata))}" if metadata else ""
    return f"## {heading}{suffix}\n\n{markdown_text(message['text'])}"


def transcript(connection, branch_id, options):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
    check_revision(branch, options.expected_revision)
    story = one(connection, "SELECT title,settings FROM stories WHERE id=?", (branch["story_id"],))
    roles = WRITING_LABELS if decode(story['settings']).get('experience') in ('directed', 'scene') else ROLE_LABELS
    passage = selected_passage(path_nodes(connection, branch["head_id"]), options)
    included = [message for message in passage if options.include_ooc or message["role"] != "ooc"]
    labels = model_labels(connection, included) if options.include_models else {}
    sections = [f"# {markdown_text(story['title'])}", f"Branch: {markdown_text(branch['name'])}"]
    sections.extend(message_markdown(message, options, labels, roles) for message in included)
    if not included:
        sections.append("No contributions are included in this selection.")
    slug = re.sub(r"[^\w-]+", "-", story["title"].lower()).strip("-")[:60] or "story"
    return {"content": "\n\n".join(sections) + "\n", "filename": f"roleplay-{slug}-{branch_id[:8]}.md",
            "branch_id": branch_id, "branch_revision": branch["revision"],
            "message_count": len(included), "omitted_ooc_count": len(passage) - len(included)}


@router.post("/branches/{branch_id}/transcript")
def preview_transcript(branch_id: str, body: TranscriptOptions, request: Request):
    with request.app.state.database.connect() as connection:
        result = transcript(connection, branch_id, body)
    checksum = hashlib.sha256((result["filename"] + "\0" + result["content"]).encode("utf-8")).hexdigest()
    with request.app.state.database.connect(write=True) as connection:
        connection.execute("INSERT OR IGNORE INTO prepared_transcripts VALUES (?,?,?,?,?)",
                           (identifier(), checksum, result["filename"], result["content"], now()))
        prepared = one(connection, "SELECT id FROM prepared_transcripts WHERE checksum=?", (checksum,))
    return {**result, "download_url": f"/api/transcripts/{prepared['id']}/download"}


@router.get("/transcripts/{transcript_id}/download")
def download_transcript(transcript_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        saved = one(connection, "SELECT filename,content FROM prepared_transcripts WHERE id=?", (transcript_id,))
    return Response(saved["content"], media_type="text/markdown", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(saved['filename'], safe='')}",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
