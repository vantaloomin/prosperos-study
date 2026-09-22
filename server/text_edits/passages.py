from server.background.storage import bind, state_id
from server.branches import insert_node, path_nodes
from server.database import identifier, now, one
from server.errors import require
from server.memory.control_state import fork_controls
from server.memory.plan_state import fork_plans
from server.passage_revisions import revised_content


def revise_text(connection, ref, text, receipt_id, name):
    source = one(connection, 'SELECT * FROM branches WHERE id=?', (ref.branch_id,))
    path = path_nodes(connection, source['head_id'], include_removed=True)
    position = next((index for index, node in enumerate(path) if node['id'] == ref.node_id), None)
    require(position is not None, 'This passage is no longer available on the selected telling.', 409)
    prefix = path[position]['parent_id']
    background = state_id(connection, prefix, node=True)
    boundary = {**source, 'head_id': prefix, 'background_state_id': background}
    replacement = None
    for index, node in enumerate(path[position:]):
        content, role, metadata = revised_content(connection, node, None)
        if index == 0:
            content = text
            metadata = {'source': 'text_edit', 'replaces': node['id'], 'edit_receipt_id': receipt_id}
            if not text:
                metadata.update(removed=True, original_node_id=node['id'], source_branch_id=source['id'])
        elif metadata.get('removed'):
            metadata['source_branch_id'] = metadata.get('source_branch_id') or source['id']
        boundary['manifest_id'] = node['manifest_id']
        boundary['head_id'] = insert_node(connection, boundary, content, role, metadata)
        if index == 0:
            replacement = boundary['head_id']
    branch_id = identifier()
    connection.execute('INSERT INTO branches VALUES (?,?,?,?,?,?,?,0,?,?)',
        (branch_id, source['story_id'], name, boundary['head_id'], source['manifest_id'], source['id'], ref.node_id, now(), now()))
    bind(connection, branch_id, background)
    fork_controls(connection, source, branch_id, prefix)
    fork_plans(connection, source, branch_id, prefix)
    connection.execute('UPDATE stories SET updated_at=? WHERE id=?', (now(), source['story_id']))
    target = ref.model_copy(update={'branch_id': branch_id, 'node_id': replacement})
    return target, {'branch_id': branch_id, 'node_id': replacement, 'source_branch_id': source['id'],
                    'source_head_id': source['head_id'], 'preserved_suffix_count': len(path) - position - 1,
                    'state_boundary_node_id': prefix}
