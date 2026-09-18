from server.database import encode, identifier, now
from server.generation_preparation import prepare_writer
from server.generations import record_generation
from server.operations import previous, remember


def saved_boundary(connection, branch):
    return connection.execute('SELECT id FROM mechanic_opportunities WHERE branch_id=? AND head_key=?',
                              (branch['id'], branch['head_id'] or '')).fetchone()


def start_assessment(connection, snapshot):
    branch = snapshot['branch']
    run_id = identifier()
    jobs = snapshot.pop('jobs')
    connection.execute('INSERT INTO assessment_runs (id,branch_id,head_key,snapshot,created_at) VALUES (?,?,?,?,?)',
                       (run_id, branch['id'], branch['head_id'] or '', encode(snapshot), now()))
    for job in jobs:
        connection.execute('INSERT INTO assessment_jobs (id,run_id,step,snapshot,status,updated_at) VALUES (?,?,?,?,?,?)',
                           (identifier(), run_id, job['step'], encode(job), 'queued', now()))
    return {'assessment_id': run_id}


def writing_request(connection, prepared):
    writer, profiles = prepared.snapshot, prepared.profiles
    branch_id = writer['branch']['id']
    branch = writer['branch']
    existing = connection.execute('SELECT * FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                  (branch_id, branch['head_id'] or '')).fetchone()
    # A request never waits for bookkeeping. Stop a late result before recording
    # the writer, in the same transaction, so completion cannot race this decision.
    if existing and not existing['generation_id'] and existing['opportunity_id'] != writer.get('opportunity_id'):
        connection.execute('UPDATE assessment_runs SET stopped=1 WHERE id=?', (existing['id'],))
    elif existing and not existing['opportunity_id']:
        connection.execute('UPDATE assessment_runs SET stopped=1 WHERE id=?', (existing['id'],))
    return record_generation(connection, writer, profiles)


class WritingRequests:
    def __init__(self, database):
        self.database = database

    def create(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump(exclude_none=True)}
        with self.database.connect() as connection:
            cached = previous(connection, body.operation_id, 'generate', payload)
            if cached is not None:
                return cached
            prepared = prepare_writer(connection, branch_id, body)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'generate', payload)
            if cached is not None:
                return cached
            prepared.validate(connection, body)
            result = writing_request(connection, prepared)
            return remember(connection, body.operation_id, 'generate', payload, result)
