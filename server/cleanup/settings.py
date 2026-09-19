from server.database import one
from server.errors import require
from server.operations import previous, remember


def settings(connection, branch_id):
    one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
    row = connection.execute('SELECT * FROM branch_cleanup_settings WHERE branch_id=?', (branch_id,)).fetchone()
    current = dict(row) if row else {'branch_id': branch_id, 'enabled': 0, 'version': 0}
    timing = connection.execute('SELECT timing FROM branch_cleanup_timing WHERE branch_id=?', (branch_id,)).fetchone()
    return {**current, 'timing': timing[0] if timing else 'before_ready'}


def frozen_settings(connection, branch_id, choices):
    current = settings(connection, branch_id)
    if not current['enabled']:
        return None
    return {**current, 'choices': choices.model_dump() if choices is not None else None}


def update(database, branch_id, body):
    payload = {'branch_id': branch_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        cached = previous(connection, body.operation_id, 'cleanup_setting', payload)
        if cached is not None:
            return cached
        current = settings(connection, branch_id)
        require(current['version'] == body.expected_version,
                'Cleanup settings changed in another window. Refresh the setting and try again.', 409)
        updated = {**current, 'enabled': int(body.enabled), 'version': current['version'] + 1, 'timing': body.timing}
        connection.execute('INSERT INTO branch_cleanup_settings VALUES (?,?,?) '
                           'ON CONFLICT(branch_id) DO UPDATE SET enabled=excluded.enabled,version=excluded.version',
                           (branch_id, updated['enabled'], updated['version']))
        connection.execute('INSERT INTO branch_cleanup_timing VALUES (?,?) '
                           'ON CONFLICT(branch_id) DO UPDATE SET timing=excluded.timing', (branch_id, body.timing))
        return remember(connection, body.operation_id, 'cleanup_setting', payload, updated)
