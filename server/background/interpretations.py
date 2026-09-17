from server.background.interpretation_context import interpretation_snapshot, preview_view
from server.background.storage import record
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.generations import Generations, stale_target
from server.operations import previous, remember
from server.workflow.context import snapshot_hash
from server.workflow.reviews import job_view


def concealed_job(row):
    snapshot = decode(row['snapshot'])
    return {key: row[key] for key in ('id', 'status', 'attempt', 'error', 'selected_state_id')} | {
        'profile_name': snapshot['profile']['name'], 'model': snapshot['profile']['config']['model'],
        'prompt_version': snapshot['prompt']['number'], 'estimated_input_tokens': snapshot['estimated_input_tokens']}


def revealed_job(row):
    view = job_view(row)
    view['targets'] = decode(view['snapshot']['content'])['targets']
    return view


def insert_run(connection, branch_id, snapshot):
    run_id, job_ids = identifier(), []
    jobs = snapshot.pop('jobs')
    connection.execute('INSERT INTO background_runs VALUES (?,?,?,?)', (run_id, branch_id, encode(snapshot), now()))
    for job in jobs:
        job_id = identifier()
        connection.execute("INSERT INTO background_jobs (id,run_id,step,snapshot,status,updated_at) VALUES (?,?,?,?,'queued',?)",
                           (job_id, run_id, job['step'], encode(job), now()))
        job_ids.append(job_id)
    return {'id': run_id, 'job_ids': job_ids}


class Interpretations:
    def __init__(self, database):
        self.database = database

    def preview(self, branch_id, body):
        with self.database.connect() as connection:
            return preview_view(interpretation_snapshot(connection, branch_id, body))

    def create(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'background_interpret', payload)
            if cached is not None:
                return cached
            snapshot = interpretation_snapshot(connection, branch_id, body)
            require(snapshot_hash(snapshot) == body.preview_hash, 'The private inputs changed. Preview these requests again.', 409)
            result = insert_run(connection, branch_id, snapshot)
            return remember(connection, body.operation_id, 'background_interpret', payload, result)

    def list(self, branch_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
            return many(connection, 'SELECT id,created_at FROM background_runs WHERE branch_id=? ORDER BY rowid DESC', (branch_id,))

    def detail(self, run_id, reveal=False):
        with self.database.connect() as connection:
            run = one(connection, 'SELECT * FROM background_runs WHERE id=?', (run_id,))
            snapshot = decode(run['snapshot'])
            _, stale = stale_target(connection, snapshot)
            jobs = many(connection, 'SELECT * FROM background_jobs WHERE run_id=? ORDER BY rowid', (run_id,))
            result = {key: run[key] for key in ('id', 'branch_id', 'created_at')}
            result.update(stale=stale, background_state_id=snapshot['background_state_id'],
                          jobs=[{**concealed_job(job), **(revealed_job(job) if reveal else {})} for job in jobs])
            return result

    def choose(self, job_id, body):
        payload = {'job_id': job_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'background_choice', payload)
            if cached is not None:
                return cached
            job = one(connection, 'SELECT * FROM background_jobs WHERE id=?', (job_id,))
            if job['selected_state_id']:
                selected = one(connection, 'SELECT id,branch_id FROM background_states WHERE id=?', (job['selected_state_id'],))
                return selected
            require(job['status'] == 'done', 'Choose a completed private interpretation.', 409)
            run = one(connection, 'SELECT * FROM background_runs WHERE id=?', (job['run_id'],))
            result = select_private_version(connection, run, job, body)
            return remember(connection, body.operation_id, 'background_choice', payload, result)

    def attempts(self, job_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM background_jobs WHERE id=?', (job_id,))
            rows = many(connection, 'SELECT * FROM background_attempts WHERE job_id=? ORDER BY attempt DESC', (job_id,))
            return [{**row, 'result': decode(row['result']), 'usage': decode(row['usage'])} for row in rows]


def select_private_version(connection, run, job, body):
    frozen = decode(run['snapshot'])
    branch, stale = stale_target(connection, frozen)
    require(not stale or body.as_new_branch, 'The Story changed. Keep this interpretation on a new branch from its original point.', 409)
    target = Generations._accept_branch(connection, branch, frozen, body)
    snapshot = decode(one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (frozen['background_state_id'],))['snapshot'])
    snapshot['manifest_id'] = target['manifest_id']
    snapshot['interpretation'] = {'run_id': run['id'], 'job_id': job['id'], 'content': decode(job['result'])}
    result = record(connection, target, snapshot, frozen['background_state_id'])
    connection.execute('UPDATE background_jobs SET selected_state_id=? WHERE id=?', (result['id'], job['id']))
    return result
