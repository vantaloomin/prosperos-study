from server.database import decode, encode, identifier, many, now, one
from server.memory.summary_service import insert_run


def insert_batch(connection, plan, kind):
    batch_id = identifier()
    snapshot = {key: plan[key] for key in ('branch', 'story_revision', 'batch_size', 'max_batches', 'eligible_count', 'selected_count')}
    snapshot['request_count'] = sum(len(run['jobs']) for run in plan['runs'])
    connection.execute("INSERT INTO summary_batches VALUES (?,?,?,?,'queued','',?,?)",
                       (batch_id, plan['branch']['id'], kind, encode(snapshot), now(), now()))
    for ordinal, run in enumerate(plan['runs']):
        result = insert_run(connection, run)
        connection.execute('INSERT INTO summary_batch_runs VALUES (?,?,?,?)', (identifier(), batch_id, result['id'], ordinal))
    return {'id': batch_id}


def batch_jobs(connection, batch_id):
    return many(connection, 'SELECT j.* FROM summary_jobs j JOIN summary_batch_runs l ON l.run_id=j.run_id '
                'WHERE l.batch_id=? ORDER BY l.ordinal,j.rowid', (batch_id,))


def batch_detail(connection, batch_id):
    row = one(connection, 'SELECT * FROM summary_batches WHERE id=?', (batch_id,))
    jobs = batch_jobs(connection, batch_id)
    links = many(connection, 'SELECT * FROM summary_batch_runs WHERE batch_id=? ORDER BY ordinal', (batch_id,))
    return {**row, 'snapshot': decode(row['snapshot']), 'runs': links,
            'requests': [{'id': job['id'], 'run_id': job['run_id'], 'status': job['status'], 'error': job['error'],
                          'profile_name': decode(job['snapshot'])['profile']['name']} for job in jobs]}


def set_batch_status(connection, batch_id, status, error=''):
    connection.execute('UPDATE summary_batches SET status=?,error=?,updated_at=? WHERE id=?', (status, error, now(), batch_id))
