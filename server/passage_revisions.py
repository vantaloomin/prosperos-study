"""Immutable path edits. All current-content readers share branches.path_nodes.

The unchanged prefix is shared. Rebuilding the suffix with fresh node identities
prevents derived facts from the old suffix from becoming evidence on the new path.
Only empty markers represent omissions; the original prose stays on the old path.
"""
from server.background.storage import bind, state_id
from server.branches import insert_node, path_nodes
from server.database import identifier, now, one
from server.errors import require
from server.memory.control_state import fork_controls
from server.memory.plan_state import fork_plans
from server.operations import previous, remember
from server.stories import check_revision


def revise_passage(database, branch_id, body):
    payload = {'branch_id': branch_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        cached = previous(connection, body.operation_id, 'passage-revision', payload)
        if cached is not None:
            return cached
        source = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        check_revision(source, body.expected_revision)
        path = path_nodes(connection, source['head_id'], include_removed=True)
        position = next((i for i, node in enumerate(path) if node['id'] == body.node_id), None)
        require(position is not None, 'This passage is not on the selected path.', 409)
        target = path[position]
        require(bool(target['metadata'].get('removed')) == (body.action == 'restore'),
                'Choose an existing passage to remove or a removal marker to undo.', 409)
        result = rebuild_suffix(connection, source, path[position:], body)
        return remember(connection, body.operation_id, 'passage-revision', payload, result)


def rebuild_suffix(connection, source, suffix, body):
    branch_id, revision_id = identifier(), identifier()
    prefix_head = suffix[0]['parent_id']
    background = state_id(connection, prefix_head, node=True)
    boundary = {**source, 'head_id': prefix_head, 'background_state_id': background}
    replacement = None
    for index, node in enumerate(suffix):
        text, role, metadata = revised_content(connection, node, body.action if index == 0 else None)
        if metadata.get('removed'):
            metadata['source_branch_id'] = metadata.get('source_branch_id') or source['id']
        boundary['manifest_id'] = node['manifest_id']
        boundary['head_id'] = insert_node(connection, boundary, text, role, metadata)
        if index == 0:
            replacement = boundary['head_id']
    connection.execute('INSERT INTO branches VALUES (?,?,?,?,?,?,?,0,?,?)',
                       (branch_id, source['story_id'], body.name, boundary['head_id'], source['manifest_id'],
                        source['id'], body.node_id, now(), now()))
    bind(connection, branch_id, background)
    fork_controls(connection, source, branch_id, prefix_head)
    fork_plans(connection, source, branch_id, prefix_head)
    connection.execute('INSERT INTO path_revisions VALUES (?,?,?,?,?,?,?)',
                       (revision_id, branch_id, source['id'], body.node_id, replacement, body.action, now()))
    connection.execute('UPDATE stories SET updated_at=? WHERE id=?', (now(), source['story_id']))
    return {'branch_id': branch_id, 'revision_id': revision_id, 'node_id': replacement,
            'source_branch_id': source['id']}


def revised_content(connection, node, action):
    original = node['metadata'].get('original_node_id', node['id'])
    metadata = {'source': 'path_revision', 'original_node_id': original}
    removed = node['metadata'].get('removed', False)
    if action == 'remove':
        removed = True
    if action == 'restore':
        node = one(connection, 'SELECT * FROM nodes WHERE id=?', (original,))
        removed = False
    if removed:
        metadata.update(removed=True, source_branch_id=node['metadata'].get('source_branch_id'))
    return ('' if removed else node['text']), node['role'], metadata
