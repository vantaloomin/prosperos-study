from server.branch_tools.comparisons import comparison_view
from server.branches import path_nodes
from server.database import decode, one
from server.errors import require
from server.side_targets import freeze, read_context
from server.text_edits.models import TextTarget
from server.text_edits.selection import apply_selection
from server.text_edits.targets import snapshot as text_snapshot


def comparison_context(connection, story_id, comparison_id):
    from server.side_context import document_parts
    record = one(connection, 'SELECT * FROM branch_comparisons WHERE id=?', (comparison_id,))
    require(record['story_id'] == story_id, 'The comparison belongs to another Story.')
    comparison = comparison_view(connection, record)
    sources = []
    for side in ('left', 'right'):
        info = comparison[side]
        for index, node in enumerate(path_nodes(connection, info['head_id'], include_removed=True)):
            title = f"{side.title()}: {info['name']} · revision {info['revision']} · message {index + 1}"
            if node['metadata'].get('removed'):
                title += ' · removed passage marker'
            sources.extend(document_parts(f"{side}:message:{node['id']}", title, node['text']))
    # Only the two frozen narrative paths enter a comparison pin. Later review,
    # memory, scene and configuration state is not evidence about those revisions.
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (record['left_branch_id'],))
    branch.update(head_id=record['left_head_id'], revision=record['left_revision'], name=comparison['left']['name'])
    story = one(connection, 'SELECT revision FROM stories WHERE id=?', (story_id,))
    return freeze(branch, story['revision'], {'kind': 'comparison', 'comparison': comparison}, sources)


def turn_context(connection, story_id, turn_id):
    row = one(connection, 'SELECT t.*,c.story_id FROM side_turns t JOIN side_threads c ON t.thread_id=c.id WHERE t.id=?', (turn_id,))
    require(row['story_id'] == story_id, 'This saved reply belongs to another Story.')
    original = decode(row['snapshot'])
    # Archive discovery may have added selected prior discussions. Their source
    # labels and disclosure classification stay frozen, never accepted as events.
    target = read_context(connection, original['context_id'])['snapshot']['target'] if original.get('context_id') else {'kind': 'turn', 'turn_id': turn_id}
    result = freeze(original['branch'], original['story_revision'], target, original['sources'])
    result['origin_turn_id'] = turn_id
    return result


def comparison_selection(connection, story_id, source):
    context = comparison_context(connection, story_id, source.comparison_id)
    comparison = context['target']['comparison']
    selected = comparison[source.side]
    node = next((item for item in path_nodes(connection, selected['head_id'], include_removed=True) if item['id'] == source.node_id), None)
    require(node is not None and not node['metadata'].get('removed'), 'Choose an existing prose passage from this comparison source.')
    apply_selection(node['text'], source.selection, 'replace', source.selection.text)
    ref = TextTarget(kind='passage', story_id=story_id, branch_id=selected['branch_id'], node_id=node['id'])
    target = text_snapshot(ref, {'revision': selected['revision'], 'head_id': selected['head_id'], 'role': node['role'], 'removed': False},
                           node['text'], f"{selected['name']} · {node['role']} passage", 100000)
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (selected['branch_id'],))
    branch.update(name=selected['name'], revision=selected['revision'], head_id=selected['head_id'])
    return freeze(branch, context['story_revision'], {'kind': 'text', 'snapshot': target, 'selection': source.selection.model_dump(), 'comparison': comparison}, context['sources'])
