"""Shared unsent questions; saving is separate from asking the Companion."""
import hashlib
import json

from pydantic import Field

from server.database import now, one
from server.errors import require
from server.text_edits.models import ExactInput


class SideDraftSave(ExactInput):
    expected_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    text: str = Field(max_length=30000)


def read_draft(connection, thread_id):
    thread = one(connection, 'SELECT * FROM side_threads WHERE id=?', (thread_id,))
    row = connection.execute('SELECT * FROM side_drafts WHERE thread_id=?', (thread_id,)).fetchone()
    revision, text = (row['revision'], row['text']) if row else (0, '')
    ref = {'kind': 'side-draft', 'story_id': thread['story_id'], 'thread_id': thread_id}
    basis = {'revision': revision}
    version = hashlib.sha256(json.dumps([ref, basis, text], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {'ref': ref, 'basis': basis, 'text': text, 'version': version, 'limit': 30000}


def write_in(connection, thread_id, text):
    connection.execute('INSERT INTO side_drafts VALUES (?,?,1,?) ON CONFLICT(thread_id) DO UPDATE SET '
                       'text=excluded.text,revision=side_drafts.revision+1,updated_at=excluded.updated_at', (thread_id, text, now()))
    return read_draft(connection, thread_id)


def save_draft(database, thread_id, body):
    with database.connect(write=True) as connection:
        current = read_draft(connection, thread_id)
        require(current['version'] == body.expected_version, 'This conversation draft changed in another view. Review both versions.', 409)
        return current if current['text'] == body.text else write_in(connection, thread_id, body.text)


def question_text(connection, thread_id, expected_version, question):
    if expected_version is None:
        return question
    current = read_draft(connection, thread_id)
    require(current['version'] == expected_version, 'This question was already sent or changed in another view. Review the conversation and current draft.', 409)
    require(bool(current['text'].strip()) and current['text'].strip() == question,
            'The question differs from the saved conversation draft. Review its exact wording.', 409)
    return current['text']


def consume_draft(connection, thread_id, expected_version, question):
    text = question_text(connection, thread_id, expected_version, question)
    if expected_version is not None:
        write_in(connection, thread_id, '')
    return text
