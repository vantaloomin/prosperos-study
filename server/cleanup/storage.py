from server.cleanup.protocol import apply_output
from server.cleanup.settings import settings
from server.database import decode, many, one
from server.errors import require
from server.memory.control_state import control_head
from server.memory.plan_state import plan_head
from server.operations import previous, remember
from server.phrases.detection import digest


def current_cleanup(connection, candidate):
    row = connection.execute('SELECT * FROM candidate_cleanups WHERE candidate_id=? AND attempt=?',
                             (candidate['id'], candidate['attempt'])).fetchone()
    return dict(row) if row else None


def still_current(connection, candidate, snapshot):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (snapshot['branch']['id'],))
    story = one(connection, 'SELECT revision FROM stories WHERE id=?', (branch['story_id'],))
    return (not candidate['accepted_node_id'] and branch['revision'] == snapshot['branch']['revision']
            and branch['head_id'] == snapshot['branch']['head_id']
            and story['revision'] == snapshot['story_revision']
            and control_head(connection, branch['id']) == snapshot.get('memory_controls_version_id')
            and plan_head(connection, branch['id']) == snapshot.get('continuity_version_id')
            and candidate['attempt'] == snapshot['attempt']
            and digest(candidate['output']) == snapshot['original_sha256'])


def permitted(connection, snapshot):
    current = settings(connection, snapshot['branch']['id'])
    return bool(current['enabled']) and current['version'] == snapshot['settings']['version']


def cleanup_view(connection, candidate, row=None):
    row = row or current_cleanup(connection, candidate)
    if row is None:
        return None
    snapshot = decode(row['snapshot'])
    return {**row, 'snapshot': snapshot, 'usage': decode(row['usage']),
            'edits': decode(row['edits']),
            'stale': not candidate['accepted_node_id'] and not still_current(connection, candidate, snapshot)}


def cleanup_rows(connection, generation_id):
    rows = many(connection, 'SELECT x.* FROM candidate_cleanups x JOIN candidates c ON c.id=x.candidate_id '
                'WHERE c.generation_id=? AND c.attempt=x.attempt', (generation_id,))
    return {row['candidate_id']: row for row in rows}


def selected_text(connection, candidate):
    cleanup = current_cleanup(connection, candidate)
    if not cleanup or cleanup['selected'] == 'original':
        return candidate['output']
    snapshot = decode(cleanup['snapshot'])
    require(cleanup['status'] == 'done' and still_current(connection, candidate, snapshot),
            'This cleanup belongs to an earlier draft or path. Choose the original before keeping it on a new branch.', 409)
    # Recheck the same evidence contract at the acceptance boundary.
    return apply_output(cleanup['output'], candidate['output'], snapshot['evidence'])[0]


def select(database, candidate_id, body):
    payload = {'candidate_id': candidate_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        cached = previous(connection, body.operation_id, 'cleanup_selection', payload)
        if cached is not None:
            return cached
        candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (candidate_id,))
        require(not candidate['accepted_node_id'], 'This draft has already been kept in the story.', 409)
        row = current_cleanup(connection, candidate)
        require(row and candidate['status'] == 'done' and candidate['attempt'] == body.expected_attempt,
                'This draft changed. Refresh before choosing its wording.', 409)
        snapshot = decode(row['snapshot'])
        require(body.original_sha256 == snapshot['original_sha256'], 'The original draft changed.', 409)
        if body.selected == 'cleaned':
            require(row['status'] == 'done' and still_current(connection, candidate, snapshot),
                    'Cleanup is not available for this draft revision.', 409)
        connection.execute('UPDATE candidate_cleanups SET selected=? WHERE id=?', (body.selected, row['id']))
        return remember(connection, body.operation_id, 'cleanup_selection', payload, {'selected': body.selected})
