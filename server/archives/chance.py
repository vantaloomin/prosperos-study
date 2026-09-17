from server.database import decode, one
from server.errors import require
from server.mechanics.state import node_state
from server.scenes.chance import chance_plan, prepare_chance
from server.scenes.state import selected_result


def validate_chance(connection, run):
    snapshot = run['snapshot']
    if not snapshot.get('chance_version'):
        require(not chance_plan(run), 'A legacy scene cannot contain an unrecorded chance schedule.')
        return
    require(snapshot['chance_version'] == 1, 'Unsupported scene chance format.')
    require(snapshot['before'] == node_state(connection, snapshot['branch']['head_id']),
            'A scene chance schedule starts from a different accepted state.')
    validate_tables(connection, snapshot)
    if run['state']['gate_a']:
        validate_schedule(connection, run)
    receipt = run['state'].get('accepted')
    if receipt and chance_plan(run):
        require(node_state(connection, receipt['node_id']) == chance_plan(run)['after'],
                'Accepted scene mechanics differ from the saved schedule.')


def validate_tables(connection, snapshot):
    for key, frozen in snapshot['tables'].items():
        row = one(connection, 'SELECT * FROM roll_table_versions WHERE id=?', (frozen['id'],))
        actual = {**row, 'definition': decode(row['definition'])}
        # Import assigns local version numbers; a saved input retains its historical label.
        content = {field: value for field, value in actual.items() if field != 'number'}
        original = {field: value for field, value in frozen.items() if field != 'number'}
        require(content == original and row['table_id'] == key, 'Saved chance uses altered frozen table definitions.')
    if snapshot['settings']['enabled']:
        require(snapshot['settings']['table_versions'] == {key: row['id'] for key, row in snapshot['tables'].items()},
                'A scene table catalog disagrees with its frozen version selections.')


def validate_schedule(connection, run):
    actual = chance_plan(run)
    plan = selected_result(connection, run, 'scene-beats')
    entries = actual['entries'] if actual else []
    scheduled = run['snapshot']['settings']['enabled'] or run['snapshot'].get('lore_context', {}).get('books')
    expected_count = len(plan['beats']) if scheduled else 0
    require(len(entries) == expected_count, 'A saved chance schedule has missing or additional boundaries.')
    seeds = iter(item['result']['seed'] for item in entries)
    expected = prepare_chance(connection, run, plan, seeds)
    require(actual == expected, 'A saved chance schedule differs from its seeds, tables or approved beats.')
