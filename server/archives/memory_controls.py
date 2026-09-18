from server.branches import path_nodes
from server.database import decode, one
from server.errors import require
from server.memory.control_models import ControlSave
from server.memory.control_service import prepare_controls
from server.memory.knowledge_evidence import chunk_identity, source_identity


def validate_controls(connection, data):
    for row in data['memory_control_versions']:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
        node = one(connection, 'SELECT * FROM nodes WHERE id=?', (row['node_id'],))
        require(branch['story_id'] == node['story_id'] == row['story_id'], 'Author decisions cross Stories.')
        payload = decode(row['payload'])
        body = ControlSave(operation_id='archive-validation', expected_revision=0, entries=[
            {**{key: value for key, value in entry.items() if key != 'sources'},
             'source_ids': [source['id'] for source in entry['sources']]} for entry in payload['entries']])
        manifest_id = payload.get('manifest_id', branch['manifest_id'])
        manifest = one(connection, 'SELECT story_id FROM manifests WHERE id=?', (manifest_id,))
        require(manifest['story_id'] == row['story_id'], 'Author decisions use another Story manifest.')
        require(prepare_controls(connection, {**branch, 'head_id': row['node_id'], 'manifest_id': manifest_id}, body) == payload,
                'Author decisions have altered or unrelated source evidence.')
        if row['parent_id']:
            parent = one(connection, 'SELECT * FROM memory_control_versions WHERE id=?', (row['parent_id'],))
            path = {node['id'] for node in path_nodes(connection, row['node_id'])}
            require(parent['story_id'] == row['story_id'] and parent['node_id'] in path, 'Author decisions inherit a foreign or future boundary.')
    for binding in data['branch_memory_controls']:
        version = one(connection, 'SELECT * FROM memory_control_versions WHERE id=?', (binding['version_id'],))
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (binding['branch_id'],))
        path = {node['id'] for node in path_nodes(connection, branch['head_id'])}
        require(branch['story_id'] == version['story_id'] and version['node_id'] in path,
                'A branch uses author decisions from another path.')


def remap_controls(payload, mapping):
    entries = []
    for entry in payload['entries']:
        sources = []
        for source in entry['sources']:
            keys = ('node_id',) if 'node_id' in source else ('asset_id', 'version_id')
            updated = {**source, **{key: mapping[source[key]] for key in keys}}
            source_id = source_identity(updated)
            sources.append({**updated, 'id': chunk_identity(source_id, source), 'source_id': source_id})
        updated_entry = {**entry, 'sources': sources}
        if entry.get('character_id'):
            updated_entry['character_id'] = mapping[entry['character_id']]
        entries.append(updated_entry)
    updated_payload = {**payload, 'entries': entries}
    if 'manifest_id' in payload:
        updated_payload['manifest_id'] = mapping[payload['manifest_id']]
    return updated_payload
