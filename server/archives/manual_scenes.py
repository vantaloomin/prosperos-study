from server.database import decode, many, one
from server.errors import require
from server.scenes.manual_acceptance import manual_material


def validate_manual_scene(connection, run):
    from server.archives.continuity import validate_acceptance_branch

    receipt = run['state']['accepted']
    material = manual_material(connection, run)
    require(material is not None and receipt.get('disabled_steps') == material['disabled_steps'],
            'Manual scene acceptance has no matching disabled stages.')
    require(not receipt.get('selected_ids') and not receipt.get('include_summary') and not receipt.get('commit_id'),
            'A manually accepted scene cannot claim generated continuity.')
    node = one(connection, 'SELECT * FROM nodes WHERE id=?', (receipt['node_id'],))
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (receipt['branch_id'],))
    origin = run['snapshot']['branch']
    require(node['parent_id'] == origin['head_id'] and node['manifest_id'] == origin['manifest_id'],
            'Manual scene acceptance changed its starting history.')
    require(node['text'] == material['text'] and node['role'] == 'assistant', 'Manual scene prose differs from its selection.')
    require(node['story_id'] == branch['story_id'] == origin['story_id'], 'Manual acceptance crosses Stories.')
    require(decode(node['metadata']) == {'source': 'manual_scene', 'scene_id': run['id'], 'disabled_steps': material['disabled_steps']},
            'Manual acceptance provenance differs from its receipt.')
    validate_acceptance_branch(connection, branch, receipt)
    decisions = many(connection, "SELECT * FROM scene_decisions WHERE run_id=? AND kind='accept'", (run['id'],))
    require(len(decisions) == 1 and decisions[0]['revision'] == run['revision'], 'Manual acceptance must be the final unique decision.')
    payload = decode(decisions[0]['payload'])
    require(payload.get('manual_review') is True and not payload.get('selected_ids') and not payload.get('include_summary'),
            'The director did not authorize manual scene acceptance.')
