from server.background.engine import guidance
from server.database import decode, encode, identifier, now, one


def state_id(connection, owner_id, node=False):
    table, key = ('node_background', 'node_id') if node else ('branch_background', 'branch_id')
    row = connection.execute(f'SELECT background_state_id FROM {table} WHERE {key}=?', (owner_id,)).fetchone()
    return row['background_state_id'] if row else None


def bind(connection, owner_id, background_id, node=False):
    if background_id is None:
        return
    table = 'node_background' if node else 'branch_background'
    connection.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)', (owner_id, background_id))


def record(connection, branch, snapshot, previous_id=None):
    value = identifier()
    connection.execute('INSERT INTO background_states VALUES (?,?,?,?,?,?,?)',
                       (value, branch['story_id'], branch['id'], branch['head_id'], previous_id, encode(snapshot), now()))
    bind(connection, branch['id'], value)
    connection.execute('UPDATE branches SET revision=revision+1,updated_at=? WHERE id=?', (now(), branch['id']))
    return {'id': value, 'branch_id': branch['id']}


def frozen_background(connection, branch_id):
    value = state_id(connection, branch_id)
    if value is None:
        return {'background_state_id': None}
    row = one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (value,))
    return {'background_state_id': value, 'private_background': guidance(decode(row['snapshot']))}


def summary(row):
    snapshot = decode(row['snapshot'])
    return {key: row[key] for key in ('id', 'branch_id', 'head_id', 'previous_id', 'created_at')} | {
        'origin': snapshot['recipe']['origin'], 'day': snapshot['day'],
        'interpreted': 'interpretation' in snapshot,
        'interpretation_run_id': snapshot.get('interpretation', {}).get('run_id'),
        'character_count': len(snapshot['recipe']['characters']), 'hook_count': snapshot['recipe']['hooks'],
        'drives_enabled': snapshot['drives_enabled'], 'hooks_enabled': snapshot['hooks_enabled']}
