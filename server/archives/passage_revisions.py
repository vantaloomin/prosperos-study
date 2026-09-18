from server.branches import path_nodes
from server.database import decode, one
from server.errors import require


def validate_passage_revisions(connection, data):
    for node in data['nodes']:
        metadata = decode(node['metadata'])
        if metadata.get('source') != 'path_revision':
            continue
        original = one(connection, 'SELECT * FROM nodes WHERE id=?', (metadata['original_node_id'],))
        require(original['story_id'] == node['story_id'] and original['role'] == node['role'],
                'A revised passage must preserve its original Story and role.')
        require(node['text'] == ('' if metadata.get('removed') else original['text']),
                'A path revision must preserve prose or use an empty removal marker.')
        if metadata.get('removed'):
            owner = one(connection, 'SELECT story_id FROM branches WHERE id=?', (metadata['source_branch_id'],))
            require(owner['story_id'] == node['story_id'], 'A removal marker crosses Stories.')
    for row in data['path_revisions']:
        validate_revision(connection, row)


def validate_revision(connection, row):
    source = one(connection, 'SELECT * FROM branches WHERE id=?', (row['source_branch_id'],))
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
    require(source['story_id'] == branch['story_id'] and branch['forked_from'] == source['id'],
            'A passage revision must belong to its original Story and path.')
    source_path = {node['id'] for node in path_nodes(connection, source['head_id'], include_removed=True)}
    revised = {node['id']: node for node in path_nodes(connection, branch['head_id'], include_removed=True)}
    require(row['source_node_id'] in source_path and row['replacement_node_id'] in revised,
            'A passage revision must link both original and revised passages.')
    replacement = revised[row['replacement_node_id']]
    require(bool(replacement['metadata'].get('removed')) == (row['action'] == 'remove'),
            'The passage revision action does not match its marker.')
