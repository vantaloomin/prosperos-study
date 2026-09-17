from server.background.engine import resolve_background
from server.database import decode, one
from server.errors import require
from server.mechanics.models import RngSettings


def same_story(connection, table, identity, story_id):
    if identity is not None:
        row = one(connection, f'SELECT story_id FROM {table} WHERE id=?', (identity,))
        require(row['story_id'] == story_id, 'Background setup crosses Stories.')


def validate_background(connection, data):
    parents = {row['id']: row['previous_id'] for row in data['background_states']}
    complete = set()
    for row in data['background_states']:
        trail, node = set(), row['id']
        while node and node not in complete:
            require(node in parents and node not in trail, 'Background history is missing or cyclic.')
            trail.add(node)
            node = parents[node]
        complete.update(trail)
        validate_state(connection, row)
    for table, key, owner in [('branch_background', 'branch_id', 'branches'), ('node_background', 'node_id', 'nodes')]:
        for row in data[table]:
            story = one(connection, f'SELECT story_id FROM {owner} WHERE id=?', (row[key],))
            same_story(connection, 'background_states', row['background_state_id'], story['story_id'])


def validate_state(connection, row):
    snapshot = decode(row['snapshot'])
    for table, key in [('branches', 'branch_id'), ('nodes', 'head_id'), ('background_states', 'previous_id')]:
        same_story(connection, table, row[key], row['story_id'])
    same_story(connection, 'manifests', snapshot['manifest_id'], row['story_id'])
    recipe = snapshot['recipe']
    require(type(snapshot['day']) is int and 0 <= snapshot['day'] <= 1000000, 'Invalid Story-relative day.')
    require(type(recipe['hooks']) is int and 0 <= recipe['hooks'] <= 8 and 1 <= recipe['horizon'] <= 3650,
            'Invalid background draw budget.')
    require(len(recipe['characters']) <= 30 and len({item['asset_id'] for item in recipe['characters']}) == len(recipe['characters']),
            'Invalid background character selection.')
    validate_characters(connection, recipe['characters'])
    settings = RngSettings.model_validate(snapshot['settings']).model_dump()
    validate_result(connection, snapshot, settings)


def validate_characters(connection, characters):
    for character in characters:
        version = one(connection, 'SELECT v.*,a.kind FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE v.id=?', (character['version_id'],))
        require(version['asset_id'] == character['asset_id'] and version['name'] == character['name'] and version['kind'] in {'character', 'persona'},
                'Background drives use a different character version.')


def validate_result(connection, snapshot, settings):
    result = snapshot['result']
    for key, frozen in result['tables'].items():
        version = one(connection, 'SELECT * FROM roll_table_versions WHERE id=?', (frozen['id'],))
        require(version['table_id'] == key and decode(version['definition']) == frozen['definition']
                and settings['table_versions'].get(key) == version['id'], 'Background table versions were altered.')
    expected = resolve_background(snapshot['recipe'], result['tables'], settings, result['seed'])
    require(result == expected, 'Background results differ from their recorded seed and tables.')
    require(type(snapshot['drives_enabled']) is bool and type(snapshot['hooks_enabled']) is bool, 'Invalid background toggles.')
    require(not snapshot['drives_enabled'] or snapshot['recipe']['characters'], 'Enabled drives have no preparation.')
    require(not snapshot['hooks_enabled'] or snapshot['recipe']['hooks'], 'Enabled hooks have no preparation.')
