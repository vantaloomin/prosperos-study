"""Branch-owned author decisions, independent of manuscript and fictional truth."""
from server.database import decode, one
from server.memory.control_sources import partition_entries


def control_head(connection, branch_id):
    row = connection.execute('SELECT version_id FROM branch_memory_controls WHERE branch_id=?', (branch_id,)).fetchone()
    return row['version_id'] if row else None


def path_node_ids(connection, head_id):
    # Decisions need membership only; loading/decoding every prose payload is wasteful.
    rows = connection.execute(
        'WITH RECURSIVE path(id,parent_id) AS (SELECT id,parent_id FROM nodes WHERE id=? '
        'UNION ALL SELECT n.id,n.parent_id FROM nodes n JOIN path p ON p.parent_id=n.id) '
        'SELECT id FROM path', (head_id,))
    return {row[0] for row in rows}


def eligible_version(connection, version_id, head_id):
    if not version_id:
        return None, set()
    path = path_node_ids(connection, head_id)
    while version_id:
        row = one(connection, 'SELECT * FROM memory_control_versions WHERE id=?', (version_id,))
        if row['node_id'] in path:
            return row, path
        version_id = row['parent_id']
    return None, path


def control_view(connection, branch):
    return controls_at(connection, branch, control_head(connection, branch['id']))


def controls_at(connection, branch, version_id):
    row, path = eligible_version(connection, version_id, branch['head_id'])
    if row is None:
        return {'version_id': version_id, 'applied_version_id': None, 'entries': []}
    entries, unavailable = partition_entries(connection, branch, decode(row['payload'])['entries'], path)
    return {'version_id': version_id, 'applied_version_id': row['id'], 'entries': entries, 'unavailable_entries': unavailable}


def fork_controls(connection, source, branch_id, head_id):
    version, _ = eligible_version(connection, control_head(connection, source['id']), head_id)
    if version:
        connection.execute('INSERT INTO branch_memory_controls VALUES (?,?)', (branch_id, version['id']))


def bind_frozen_controls(connection, branch_id, snapshot):
    version_id = snapshot.get('memory_controls_version_id')
    if version_id:
        connection.execute('INSERT INTO branch_memory_controls VALUES (?,?)', (branch_id, version_id))
