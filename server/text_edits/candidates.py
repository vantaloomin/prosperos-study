from server.database import decode, identifier, now, one
from server.errors import require
from server.phrases.detection import digest
from server.text_edits.models import TextTarget
from server.text_edits.targets import snapshot


def draft_head(connection, candidate):
    row = connection.execute('SELECT * FROM candidate_text_heads WHERE candidate_id=? AND attempt=?',
                             (candidate['id'], candidate['attempt'])).fetchone()
    return dict(row) if row else None


def source_candidate(connection, ref):
    candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (ref.candidate_id,))
    generation = one(connection, 'SELECT branch_id FROM generations WHERE id=?', (candidate['generation_id'],))
    branch = one(connection, 'SELECT story_id,name FROM branches WHERE id=?', (generation['branch_id'],))
    require(generation['branch_id'] == ref.branch_id and branch['story_id'] == ref.story_id,
            'This draft belongs to another Story or telling.', 409)
    return candidate, branch


def candidate_snapshot(connection, ref):
    from server.cleanup.storage import current_cleanup, still_current
    candidate, branch = source_candidate(connection, ref)
    require(candidate['status'] == 'done', 'Finish this draft before reviewing a text change.', 409)
    head = draft_head(connection, candidate)
    text, cleanup_id = candidate['output'], None
    cleanup = current_cleanup(connection, candidate)
    if head:
        text = head['text']
    elif cleanup and cleanup['status'] == 'done' and cleanup['selected'] == 'cleaned':
        if still_current(connection, candidate, decode(cleanup['snapshot'])) or candidate['accepted_node_id']:
            text, cleanup_id = cleanup['cleaned'], cleanup['id']
    basis = {'revision': head['revision'] if head else 0, 'draft_id': head['id'] if head else None,
             'attempt': candidate['attempt'], 'original_sha256': digest(candidate['output']),
             'edit_receipt_id': head['receipt_id'] if head else None, 'cleanup_id': cleanup_id}
    return snapshot(ref, basis, text, f"{branch['name']} · unaccepted draft", 100000)


def require_unaccepted(connection, ref):
    candidate, _ = source_candidate(connection, ref)
    require(not candidate['accepted_node_id'], 'This draft has already been kept. Open its accepted passage in the Story to revise that text.', 409)
    require(candidate['status'] == 'done', 'Only completed, unaccepted drafts can be edited.', 409)


def publish_candidate(connection, ref, text, receipt_id):
    require_unaccepted(connection, ref)
    candidate, _ = source_candidate(connection, ref)
    head = draft_head(connection, candidate)
    if head:
        connection.execute('UPDATE candidate_text_heads SET revision=revision+1,text=?,receipt_id=?,updated_at=? WHERE id=?',
                           (text, receipt_id, now(), head['id']))
        draft_id = head['id']
    else:
        draft_id = identifier()
        connection.execute('INSERT INTO candidate_text_heads VALUES (?,?,?,1,?,?,?,?)',
                           (draft_id, candidate['id'], candidate['attempt'], text, receipt_id, now(), now()))
    return ref, {'candidate_id': candidate['id'], 'draft_id': draft_id, 'attempt': candidate['attempt']}


def wording_view(connection, candidate, branch_id, story_id):
    if candidate['status'] != 'done':
        return {'text_edit': None, 'wording_version': None}
    ref = TextTarget(kind='candidate', story_id=story_id, branch_id=branch_id, candidate_id=candidate['id'])
    return {'text_edit': draft_head(connection, candidate), 'wording_version': candidate_snapshot(connection, ref)['version']}


def acceptance_edit(connection, candidate, snapshot, expected_version):
    ref = TextTarget(kind='candidate', story_id=snapshot['branch']['story_id'], branch_id=snapshot['branch']['id'], candidate_id=candidate['id'])
    head = draft_head(connection, candidate)
    require(not head or expected_version, 'Review the current author revision before keeping this draft.', 409)
    if expected_version:
        require(candidate_snapshot(connection, ref)['version'] == expected_version,
                'This draft wording changed in another view. Review the current text before keeping it.', 409)
    return {'edit_receipt_id': head['receipt_id']} if head else {}
