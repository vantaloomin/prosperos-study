from server.database import now, one
from server.errors import require
from server.operations import previous, remember


def curation(connection, branch_id):
    row = connection.execute('SELECT * FROM branch_curation WHERE branch_id=?', (branch_id,)).fetchone()
    return {'favorite': bool(row['favorite']), 'archived': bool(row['archived']), 'revision': row['revision']} if row else {
        'favorite': False, 'archived': False, 'revision': 0}


def story_branches(connection, story_id):
    rows = connection.execute('SELECT b.*,c.favorite,c.archived,c.revision AS curation_revision FROM branches b '
                              'LEFT JOIN branch_curation c ON c.branch_id=b.id WHERE b.story_id=? '
                              'ORDER BY b.created_at,b.id', (story_id,))
    result = []
    for raw in rows:
        row = dict(raw)
        state = {'favorite': bool(row.pop('favorite')), 'archived': bool(row.pop('archived')),
                 'revision': row.pop('curation_revision') or 0}
        result.append({**row, 'curation': state})
    return result


def update_curation(database, branch_id, body):
    payload = {'branch_id': branch_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        saved = previous(connection, body.operation_id, 'branch-curation', payload)
        if saved is not None:
            return saved
        one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
        current = curation(connection, branch_id)
        require(current['revision'] == body.expected_revision, 'This branch was organized in another view. Refresh first.', 409)
        connection.execute('INSERT INTO branch_curation VALUES (?,?,?,?,?) ON CONFLICT(branch_id) DO UPDATE SET '
                           'favorite=excluded.favorite,archived=excluded.archived,revision=excluded.revision,updated_at=excluded.updated_at',
                           (branch_id, body.favorite, body.archived, current['revision'] + 1, now()))
        return remember(connection, body.operation_id, 'branch-curation', payload, curation(connection, branch_id))
