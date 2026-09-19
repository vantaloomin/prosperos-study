from server.database import decode, encode, identifier, many, now, one
from server.memory.relationship_context import plan_requests
from server.operations import previous, remember


def insert_jobs(connection, plan, mode):
    ids = []
    for snapshot in plan['snapshots']:
        identity = identifier()
        connection.execute('INSERT INTO relationship_jobs (id,branch_id,request_key,mode,snapshot,status,created_at,updated_at) '
                           "VALUES (?,?,?,?,?,'queued',?,?)",
                           (identity, snapshot['branch']['id'], snapshot['request_key'], mode, encode(snapshot), now(), now()))
        ids.append(identity)
    return {**{key: value for key, value in plan.items() if key != 'snapshots'}, 'job_ids': ids}


def create_jobs(database, branch_id, body):
    payload = {'branch_id': branch_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        cached = previous(connection, body.operation_id, 'relationship-prepare', payload)
        if cached is not None:
            return cached
        plan = plan_requests(connection, branch_id, body.expected_revision)
        return remember(connection, body.operation_id, 'relationship-prepare', payload, insert_jobs(connection, plan, 'manual'))


def job_detail(database, identity):
    with database.connect() as connection:
        row = one(connection, 'SELECT * FROM relationship_jobs WHERE id=?', (identity,))
        snapshot = decode(row['snapshot'])
        snapshot['profile'].pop('credential_ref', None)
        return {**row, 'snapshot': snapshot, 'result': decode(row['result']), 'usage': decode(row['usage'])}


def recent_jobs(database, branch_id):
    with database.connect() as connection:
        one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
        rows = many(connection, 'SELECT id,status,mode,error,usage,created_at FROM relationship_jobs WHERE branch_id=? '
                    'ORDER BY rowid DESC LIMIT 30', (branch_id,))
        return [{**row, 'usage': decode(row['usage'])} for row in rows]
