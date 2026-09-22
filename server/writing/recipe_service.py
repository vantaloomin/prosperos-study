from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.operations import previous, remember
from server.text_edits.models import TextTarget
from server.text_edits.service import create_in, proposal_view
from server.text_edits.targets import check_current
from server.workflow.context import snapshot_hash
from server.writing.recipe_bindings import initial_bindings, public_value
from server.writing.recipe_chance import resolve_chance
from server.writing.recipe_plan import prepare_recipe
from server.writing.recipe_state import next_jobs, progress, read_jobs, read_run, step_preview


def finish_recipe(connection, run_id):
    run, jobs = read_run(connection, run_id), read_jobs(connection, run_id)
    state = progress(run, jobs)
    if state['status'] != 'complete' or not state['last_prose']:
        return
    if connection.execute('SELECT 1 FROM recipe_results WHERE run_id=?', (run_id,)).fetchone():
        return
    job = next(job for job in jobs if job['id'] == state['last_prose'])
    result = job['result']
    status = 'pending'
    try:
        check_current(connection, TextTarget.model_validate(run['target']['ref']), run['target']['version'])
    except DomainError:
        status = 'conflict'
    proposal = create_in(connection, run['target'], run['snapshot']['selection'], run['snapshot']['action'],
                         result['replacement'], result['explanation'], status=status,
                         origin={'kind': 'recipe', 'run_id': run_id, 'job_id': job['id']})
    connection.execute('INSERT INTO recipe_results VALUES (?,?,?)', (run_id, job['id'], proposal['id']))


class RecipeRuns:
    def __init__(self, database):
        self.database = database

    def create(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'recipe-run', payload)
            if cached is not None:
                return cached
            snapshot = prepare_recipe(connection, branch_id, body)
            require(snapshot_hash(snapshot) == body.preview_hash, 'The recipe inputs changed. Preview the complete workflow again.', 409)
            identity = identifier()
            chance = resolve_chance(snapshot['chance'])
            connection.execute('INSERT INTO recipe_runs VALUES (?,?,?,?,?,?,?,0,?)',
                (identity, snapshot['branch']['story_id'], branch_id, encode(snapshot), encode(initial_bindings(snapshot)),
                 encode(snapshot['target']), encode(chance), now()))
            return remember(connection, body.operation_id, 'recipe-run', payload, {'id': identity})

    def preview_step(self, run_id):
        with self.database.connect() as connection:
            return public_value(step_preview(connection, read_run(connection, run_id), read_jobs(connection, run_id)))

    def start_step(self, run_id, body):
        payload = {'run_id': run_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'recipe-step', payload)
            if cached is not None:
                return cached
            run = read_run(connection, run_id)
            require(run['revision'] == body.expected_revision, 'Another view advanced this recipe. Open its recorded step.', 409)
            prepared = next_jobs(connection, run, read_jobs(connection, run_id))
            require(snapshot_hash(prepared) == body.preview_hash, 'The recipe step inputs changed. Preview them again.', 409)
            ids = []
            for snapshot in prepared['jobs']:
                identity = identifier()
                connection.execute('INSERT INTO recipe_jobs (id,run_id,stage,step,snapshot,status,updated_at) VALUES (?,?,?,?,?,\'queued\',?)',
                    (identity, run_id, prepared['stage'], snapshot['step'], encode(snapshot), now()))
                ids.append(identity)
            connection.execute('UPDATE recipe_runs SET revision=revision+1 WHERE id=?', (run_id,))
            return remember(connection, body.operation_id, 'recipe-step', payload, {'id': run_id, 'job_ids': ids})

    def detail(self, run_id):
        with self.database.connect() as connection:
            run, jobs = read_run(connection, run_id), read_jobs(connection, run_id)
            result = connection.execute('SELECT proposal_id FROM recipe_results WHERE run_id=?', (run_id,)).fetchone()
            proposals = many(connection, "SELECT id FROM text_edit_proposals WHERE json_extract(origin,'$.kind')='recipe' "
                             "AND json_extract(origin,'$.run_id')=? ORDER BY created_at,id", (run_id,))
            return public_value({**run, 'jobs': jobs, 'progress': progress(run, jobs),
                'proposal_id': result['proposal_id'] if result else None,
                'proposals': [proposal_view(connection, item['id']) for item in proposals]})

    def list(self, branch_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
            rows = many(connection, 'SELECT id,created_at,revision,json_extract(snapshot,\'$.guidance.recipe.name\') AS name '
                        'FROM recipe_runs WHERE branch_id=? ORDER BY rowid DESC LIMIT 100', (branch_id,))
            return [{**row, 'status': progress(read_run(connection, row['id']), read_jobs(connection, row['id']))['status']} for row in rows]

    def operation(self, operation_id):
        with self.database.connect() as connection:
            row = connection.execute("SELECT result FROM operations WHERE id=? AND kind IN ('recipe-run','recipe-step')", (operation_id,)).fetchone()
            return decode(row['result']) if row else None

    def attempts(self, job_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM recipe_jobs WHERE id=?', (job_id,))
            return [{**row, 'result': decode(row['result']), 'usage': decode(row['usage'])} for row in many(
                connection, 'SELECT * FROM recipe_attempts WHERE job_id=? ORDER BY attempt', (job_id,))]
