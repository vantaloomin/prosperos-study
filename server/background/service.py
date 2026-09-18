import secrets

from server.background.engine import resolve_background
from server.background.storage import record, state_id, summary
from server.database import decode, identifier, many, now, one
from server.errors import require
from server.manifests import manifest_view
from server.mechanics.config import configured_tables, read_settings
from server.memory.control_state import bind_frozen_controls, control_head
from server.operations import previous, remember
from server.stories import check_revision


def recipe_for(connection, branch, body):
    attached = {item['asset_id']: item for item in manifest_view(connection, branch['manifest_id'])
                if item['kind'] in {'character', 'persona'} and item['enabled']}
    require(set(body.character_ids) <= set(attached), 'Choose active supporting characters attached to this path.')
    characters = [{'asset_id': key, 'version_id': attached[key]['version_id'], 'name': attached[key]['version']['name']}
                  for key in body.character_ids]
    return {'characters': characters, 'hooks': body.hooks, 'origin': body.origin,
            'day': body.day, 'horizon': body.horizon}


def initial_snapshot(connection, branch, body):
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    settings = read_settings(story)
    versions = configured_tables(connection, settings)
    settings.table_versions = {key: item['id'] for key, item in versions.items()}
    recipe = recipe_for(connection, branch, body)
    result = resolve_background(recipe, versions, settings.model_dump(), secrets.token_hex(16))
    return {'recipe': recipe, 'settings': settings.model_dump(), 'result': result,
            'memory_controls_version_id': control_head(connection, branch['id']),
            'drives_enabled': bool(recipe['characters']), 'hooks_enabled': bool(recipe['hooks']), 'day': body.day}


def reroll(connection, source, body):
    original = one(connection, 'SELECT * FROM background_states WHERE id=?', (body.reroll_of,))
    require(original['story_id'] == source['story_id'], 'Choose background setup from this Story.')
    snapshot = decode(original['snapshot'])
    origin = one(connection, 'SELECT * FROM branches WHERE id=?', (original['branch_id'],))
    manifest_id = snapshot['manifest_id']
    target = {**origin, 'id': identifier(), 'head_id': original['head_id'], 'manifest_id': manifest_id, 'revision': 0}
    connection.execute('INSERT INTO branches VALUES (?,?,?,?,?,?,?,0,?,?)',
                       (target['id'], source['story_id'], body.branch_name, target['head_id'], manifest_id,
                        origin['id'], target['head_id'], now(), now()))
    bind_frozen_controls(connection, target['id'], snapshot)
    snapshot['result'] = resolve_background(snapshot['recipe'], snapshot['result']['tables'], snapshot['settings'], secrets.token_hex(16))
    snapshot.pop('interpretation', None)
    return target, snapshot


class Background:
    def __init__(self, database):
        self.database = database

    def context(self, branch_id):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            current = state_id(connection, branch_id)
            rows = many(connection, 'WITH RECURSIVE lineage AS (SELECT * FROM background_states WHERE branch_id=? OR id=? '
                        'UNION SELECT s.* FROM background_states s JOIN lineage l ON s.id=l.previous_id) '
                        'SELECT * FROM lineage ORDER BY created_at DESC', (branch_id, current))
            return {'current': current, 'revision': branch['revision'], 'history': [summary(row) for row in rows]}

    def reveal(self, background_id):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT * FROM background_states WHERE id=?', (background_id,))
            return {**row, 'snapshot': decode(row['snapshot'])}

    def prepare(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            receipt = previous(connection, body.operation_id, 'background_prepare', payload)
            if receipt is not None:
                return receipt
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            check_revision(branch, body.expected_revision)
            require(body.reroll_of or state_id(connection, branch_id) is None,
                    'This path already has background setup. Reuse it or reroll on another branch.', 409)
            target, snapshot = reroll(connection, branch, body) if body.reroll_of else (branch, initial_snapshot(connection, branch, body))
            snapshot['manifest_id'] = target['manifest_id']
            result = record(connection, target, snapshot, body.reroll_of)
            return remember(connection, body.operation_id, 'background_prepare', payload, result)

    def update(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            receipt = previous(connection, body.operation_id, 'background_update', payload)
            if receipt is not None:
                return receipt
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            check_revision(branch, body.expected_revision)
            current = state_id(connection, branch_id)
            require(current is not None, 'Prepare background setup first.', 409)
            snapshot = decode(one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (current,))['snapshot'])
            require(not body.drives_enabled or snapshot['recipe']['characters'], 'No character drives were prepared.')
            require(not body.hooks_enabled or snapshot['recipe']['hooks'], 'No future hooks were prepared.')
            snapshot.update(day=body.day, drives_enabled=body.drives_enabled, hooks_enabled=body.hooks_enabled)
            snapshot['manifest_id'] = branch['manifest_id']
            result = record(connection, branch, snapshot, current)
            return remember(connection, body.operation_id, 'background_update', payload, result)
