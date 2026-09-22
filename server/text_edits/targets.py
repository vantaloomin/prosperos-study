import hashlib
import json

from server.branches import path_nodes
from server.database import identifier, now, one
from server.errors import require

DOCUMENT_LIMITS = {'composer': 100000, 'author-note': 100000, 'scene-goal': 30000}


def snapshot_version(value):
    content = json.dumps({key: value[key] for key in ('ref', 'basis', 'text')}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def snapshot(ref, basis, text, label, limit):
    value = {'ref': ref.model_dump(exclude_none=True), 'basis': basis, 'text': text, 'label': label, 'limit': limit}
    return {**value, 'version': snapshot_version(value)}


def read_target(connection, ref):
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (ref.story_id,))
    if ref.kind == 'scene-block':
        from server.text_edits.scenes import scene_snapshot
        return scene_snapshot(connection, ref)
    if ref.kind == 'candidate':
        from server.text_edits.candidates import candidate_snapshot
        return candidate_snapshot(connection, ref)
    from server.text_edits.versioned import VERSIONED_KINDS, current_version, edition_snapshot
    if ref.kind in VERSIONED_KINDS:
        return edition_snapshot(ref, current_version(connection, ref))
    if ref.kind == 'story-brief':
        return snapshot(ref, {'revision': story['revision']}, story['premise'], f"{story['title']} · Story brief", 30000)
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (ref.branch_id,))
    require(branch['story_id'] == ref.story_id, 'The selected target belongs to another Story.', 409)
    if ref.kind == 'document':
        row = connection.execute('SELECT * FROM text_documents WHERE branch_id=? AND purpose=?', (branch['id'], ref.purpose)).fetchone()
        basis = {'revision': row['revision'] if row else 0, 'document_id': row['id'] if row else None}
        return snapshot(ref, basis, row['text'] if row else '', f"{branch['name']} · {ref.purpose}", DOCUMENT_LIMITS[ref.purpose])
    node = next((item for item in path_nodes(connection, branch['head_id'], include_removed=True) if item['id'] == ref.node_id), None)
    require(node is not None, 'This passage is not on the selected telling.', 409)
    basis = {'revision': branch['revision'], 'head_id': branch['head_id'], 'role': node['role'], 'removed': bool(node['metadata'].get('removed'))}
    return snapshot(ref, basis, node['text'], f"{branch['name']} · {node['role']} passage", 100000)


def check_current(connection, ref, expected_version):
    if ref.kind == 'scene-block':
        from server.text_edits.scenes import require_scene_editable
        require_scene_editable(connection, ref)
    if ref.kind == 'candidate':
        from server.text_edits.candidates import require_unaccepted
        require_unaccepted(connection, ref)
    current = read_target(connection, ref)
    require(current['version'] == expected_version, 'This target changed. Review the current text and explicitly rebase the proposal.', 409)
    return current


def save_document(connection, ref, text):
    require(ref.kind == 'document', 'Choose an unsent text document.')
    require(len(text) <= DOCUMENT_LIMITS[ref.purpose], 'This text exceeds the destination limit.')
    row = connection.execute('SELECT * FROM text_documents WHERE branch_id=? AND purpose=?', (ref.branch_id, ref.purpose)).fetchone()
    if row is None:
        connection.execute('INSERT INTO text_documents VALUES (?,?,?,?,?,1,?)', (identifier(), ref.story_id, ref.branch_id, ref.purpose, text, now()))
    elif row['text'] != text:
        connection.execute('UPDATE text_documents SET text=?,revision=revision+1,updated_at=? WHERE id=?', (text, now(), row['id']))
    return read_target(connection, ref)


def write_target(connection, ref, text, receipt_id, branch_name, database=None):
    if ref.kind == 'scene-block':
        from server.text_edits.scenes import publish_scene_block
        return publish_scene_block(connection, ref, text, receipt_id)
    if ref.kind == 'candidate':
        from server.text_edits.candidates import publish_candidate
        return publish_candidate(connection, ref, text, receipt_id)
    from server.text_edits.versioned import VERSIONED_KINDS, publish_field
    if ref.kind in VERSIONED_KINDS:
        return publish_field(connection, database, ref, text)
    if ref.kind == 'passage':
        from server.text_edits.passages import revise_text
        return revise_text(connection, ref, text, receipt_id, branch_name)
    if ref.kind == 'document':
        current = save_document(connection, ref, text)
        return ref, {'document_id': current['basis']['document_id']}
    require(len(text) <= 30000, 'Story briefs are limited to 30,000 characters.')
    connection.execute('UPDATE stories SET premise=?,revision=revision+1,updated_at=? WHERE id=?', (text, now(), ref.story_id))
    return ref, {'story_id': ref.story_id}
