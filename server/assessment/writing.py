from server.agent_switches import agent_enabled
from server.assessment.context import assessment_needed, assessment_plan, seed_assessment
from server.database import decode, encode, identifier, now, one
from server.errors import require
from server.generation_models import semantic_request
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


def writing_request(connection, prepared, plan, body):
    writer, profiles = prepared.snapshot, prepared.profiles
    branch_id = writer['branch']['id']
    branch = writer['branch']
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    existing = connection.execute('SELECT * FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                  (branch_id, branch['head_id'] or '')).fetchone()
    if not agent_enabled(connection, 'beat-assessment', story) or not assessment_needed(story, writer, body) or saved_boundary(connection, branch):
        if existing and not existing['generation_id']:
            connection.execute('UPDATE assessment_runs SET stopped=1 WHERE id=?', (existing['id'],))
        return record_generation(connection, writer, profiles)
    if existing:
        if existing['generation_id']:
            return record_generation(connection, writer, profiles)
        frozen = decode(existing['snapshot'])
        require(frozen['request'] == semantic_request(body),
                'An assessment is already saved at this point. Reopen it, or explicitly continue without assessment.', 409)
        return {'assessment_id': existing['id']}
    require(plan is not None, 'The assessment inputs changed. Refresh the request.', 409)
    return start_assessment(connection, seed_assessment(plan))


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
            plan = prepare_assessment(connection, prepared, body)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'generate', payload)
            if cached is not None:
                return cached
            prepared.validate(connection, body)
            result = writing_request(connection, prepared, plan, body)
            return remember(connection, body.operation_id, 'generate', payload, result)


def prepare_assessment(connection, prepared, body):
    writer = prepared.snapshot
    branch = writer['branch']
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    existing = connection.execute('SELECT id FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                  (branch['id'], branch['head_id'] or '')).fetchone()
    needed = agent_enabled(connection, 'beat-assessment', story) and assessment_needed(story, writer, body)
    if not needed or existing or saved_boundary(connection, branch):
        return None
    return assessment_plan(connection, story, writer, prepared.profiles, body)
