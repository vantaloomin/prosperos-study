"""Author-owned conversation labels and browsing; never writer context."""
import re

from pydantic import Field

from server.database import many, now, one
from server.errors import require
from server.models import Input
from server.operations import previous, remember


class SideThreadUpdate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=120)
    archived: bool


def organization(connection, thread_id):
    row = connection.execute('SELECT archived,revision FROM side_thread_curation WHERE thread_id=?', (thread_id,)).fetchone()
    return {'archived': bool(row['archived']), 'revision': row['revision']} if row else {'archived': False, 'revision': 0}


def thread_rows(connection, story_id, include_archived=False):
    one(connection, 'SELECT id FROM stories WHERE id=?', (story_id,))
    rows = many(connection, 'SELECT t.*,c.archived,c.revision AS curation_revision FROM side_threads t '
                'LEFT JOIN side_thread_curation c ON c.thread_id=t.id WHERE t.story_id=? '
                'ORDER BY t.created_at DESC,t.id', (story_id,))
    result = []
    for row in rows:
        curation = {'archived': bool(row.pop('archived')), 'revision': row.pop('curation_revision') or 0}
        if include_archived or not curation['archived']:
            result.append({**row, 'curation': curation})
    return result


def update_thread(database, thread_id, body):
    payload = {'thread_id': thread_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        saved = previous(connection, body.operation_id, 'side-organization', payload)
        if saved is not None:
            return saved
        one(connection, 'SELECT id FROM side_threads WHERE id=?', (thread_id,))
        state = organization(connection, thread_id)
        require(state['revision'] == body.expected_revision, 'This conversation changed in another view. Refresh its details.', 409)
        connection.execute('UPDATE side_threads SET name=? WHERE id=?', (body.name, thread_id))
        connection.execute('INSERT INTO side_thread_curation VALUES (?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET '
                           'archived=excluded.archived,revision=excluded.revision,updated_at=excluded.updated_at',
                           (thread_id, body.archived, state['revision'] + 1, now()))
        return remember(connection, body.operation_id, 'side-organization', payload,
                        {'id': thread_id, 'name': body.name, 'curation': organization(connection, thread_id)})


def snippet(pattern, text, kind, turn_id=None):
    found = pattern.search(text)
    if not found:
        return None
    start, end = found.span()
    return {'kind': kind, 'turn_id': turn_id, 'reply_id': None, 'before': text[max(0, start - 80):start],
            'match': text[start:end], 'after': text[end:end + 160],
            'truncated_before': start > 80, 'truncated_after': end + 160 < len(text)}


def search_threads(connection, story_id, query, include_archived=False, offset=0, limit=30):
    rows = thread_rows(connection, story_id, include_archived)
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matched = content_matches(connection, story_id, {row['id'] for row in rows}, pattern) if query else {}
    for row in rows:
        match = snippet(pattern, row['name'], 'name') or matched.get(row['id']) if query else None
        if not query or match:
            results.append({**row, 'match': match})
    return {'total': len(results), 'results': results[offset:offset + limit],
            'next_offset': offset + limit if offset + limit < len(results) else None}


def content_matches(connection, story_id, eligible, pattern):
    found = {}
    rows = connection.execute('SELECT t.id,t.thread_id,t.question,r.output,r.id AS reply_id FROM side_turns t '
        'JOIN side_threads c ON c.id=t.thread_id LEFT JOIN side_replies r ON r.turn_id=t.id '
        'WHERE c.story_id=? ORDER BY t.created_at DESC,t.id,r.rowid', (story_id,))
    for row in rows:
        thread_id = row['thread_id']
        if thread_id in found or thread_id not in eligible:
            continue
        match = snippet(pattern, row['question'], 'question', row['id']) or snippet(pattern, row['output'] or '', 'reply', row['id'])
        if match:
            if match['kind'] == 'reply':
                match['reply_id'] = row['reply_id']
            found[thread_id] = match
    return found
