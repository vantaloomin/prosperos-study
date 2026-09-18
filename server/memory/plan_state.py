"""Versioned author corrections folded into the same accepted-continuity view."""
from server.database import many, one
from server.memory.control_state import path_node_ids


def plan_head(connection, branch_id):
    row = connection.execute('SELECT version_id FROM branch_continuity_edits WHERE branch_id=?', (branch_id,)).fetchone()
    return row['version_id'] if row else None


def author_edits(connection, version_id, head_id):
    if not version_id:
        return []
    path = path_node_ids(connection, head_id)
    rows = many(connection, 'WITH RECURSIVE edits AS (SELECT *,0 AS distance FROM continuity_edits WHERE id=? '
                'UNION ALL SELECT e.*,p.distance+1 FROM continuity_edits e JOIN edits p ON e.id=p.parent_id) '
                'SELECT * FROM edits ORDER BY distance DESC', (version_id,))
    return [{key: value for key, value in row.items() if key != 'distance'} for row in rows if row['node_id'] in path]


def bind_plan_head(connection, branch_id, version_id):
    if version_id:
        connection.execute('INSERT INTO branch_continuity_edits VALUES (?,?) '
                           'ON CONFLICT(branch_id) DO UPDATE SET version_id=excluded.version_id', (branch_id, version_id))


def fork_plans(connection, source, branch_id, head_id):
    edits = author_edits(connection, plan_head(connection, source['id']), head_id)
    if edits:
        bind_plan_head(connection, branch_id, edits[-1]['id'])


def validate_plan_head(connection, branch, version_id):
    if not version_id:
        return
    row = one(connection, 'SELECT * FROM continuity_edits WHERE id=?', (version_id,))
    owner = one(connection, 'SELECT story_id FROM branches WHERE id=?', (row['branch_id'],))
    path = path_node_ids(connection, branch['head_id'])
    from server.errors import require
    require(owner['story_id'] == branch['story_id'] and row['node_id'] in path,
            'Continuity edits belong to another Story or a later path.', 409)
