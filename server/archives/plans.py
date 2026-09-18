"""Validate author plan journals and frozen continuity boundaries before restore."""
from server.database import decode, one
from server.errors import require
from server.memory.plan_edits import validate_author_change
from server.memory.plan_state import validate_plan_head
from server.scenes.continuity_models import ContinuityChange


def validate_plan_edits(connection, data):
    origins = set()
    for row in data['continuity_edits']:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
        node = one(connection, 'SELECT * FROM nodes WHERE id=?', (row['node_id'],))
        require(branch['story_id'] == node['story_id'], 'A plan edit crosses Stories.')
        origin = (branch['story_id'], row['origin_id'])
        require(len(row['origin_id']) == 32 and all(c in '0123456789abcdef' for c in row['origin_id'])
                and origin not in origins, 'A plan edit has an invalid or duplicated identity.')
        origins.add(origin)
        boundary = {**branch, 'head_id': row['node_id']}
        validate_plan_head(connection, boundary, row['parent_id'])
        changes = decode(row['changes'])
        require(isinstance(changes, list) and len(changes) == 1, 'An author plan edit must contain one explicit change.')
        change = ContinuityChange.model_validate(changes[0]).model_dump()
        require(change == changes[0], 'An author plan edit has changed its structured fields.')
        validate_author_change(connection, row['node_id'], row['parent_id'], change)
    for binding in data['branch_continuity_edits']:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (binding['branch_id'],))
        validate_plan_head(connection, branch, binding['version_id'])
    for table in ('generations', 'scene_runs', 'review_runs'):
        for row in data[table]:
            snapshot = decode(row['snapshot'])
            validate_plan_head(connection, snapshot['branch'], snapshot.get('continuity_version_id'))
            if table == 'generations':
                validate_writer_plans(connection, snapshot)
    for row in data['assessment_runs']:
        snapshot = decode(row['snapshot'])['writer_snapshot']
        validate_plan_head(connection, snapshot['branch'], snapshot.get('continuity_version_id'))
        validate_writer_plans(connection, snapshot)


def validate_writer_plans(connection, snapshot):
    from server.continuity import continuity_values, continuity_view
    from server.memory.plan_packet import PLAN_RULE, compact_plan
    if 'continuity_version_id' not in snapshot or 'knowledge_lens' in snapshot:
        return
    content = decode(snapshot['content'])
    expected = continuity_view(connection, snapshot['branch']['head_id'], snapshot['continuity_version_id'])
    entries = expected['entries']
    layer = content.get('plan_memory')
    if layer is None:
        require([continuity_values(item) for item in content.get('continuity', {}).get('entries', [])] ==
                [continuity_values(item) for item in entries], 'Writer continuity differs from its frozen accepted path.')
        return
    require(content['story']['settings'].get('memory', {}).get('mode') == 'long',
            'Only Long story mode can omit plans.')
    require([continuity_values(item) for item in content['continuity']['entries']] ==
            [continuity_values(item) for item in entries if item['kind'] != 'plan'],
            'Writer context omitted or changed other required continuity.')
    plans = {item['id']: item for item in entries if item['kind'] == 'plan'}
    selected = [item['id'] for item in layer['entries']]
    require(len(set(selected)) == len(selected) and set(selected) <= plans.keys(), 'Writer selected duplicate or foreign plans.')
    omitted = [entry_id for entry_id in plans if entry_id not in selected]
    require(layer == {'rule': PLAN_RULE, 'entries': [compact_plan(plans[key]) for key in selected],
                      'omitted_count': len(omitted)}, 'Writer plan state or evidence differs from its recorded source.')
    require(snapshot.get('memory', {}).get('plans') == {'version': 1, 'available': len(plans),
            'selected_ids': selected, 'omitted_ids': omitted}, 'Writer plan coverage is incomplete or misleading.')
