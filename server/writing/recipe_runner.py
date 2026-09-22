import time
from contextlib import aclosing
from dataclasses import asdict

from server.database import decode, encode, now, one
from server.errors import DomainError, require
from server.providers.completion import StreamCompletion
from server.text_edits.service import proposed_text
from server.workflow.runner import ReviewRunner, preserve_attempt
from server.writing.recipe_output import parse_recipe_output
from server.writing.recipe_service import finish_recipe
from server.writing.recipe_state import read_run, require_current_ceiling


class RecipeRunner(ReviewRunner):
    prefix = 'recipe'
    label = 'recipe step'

    def parse_result(self, output, snapshot):
        return parse_recipe_output(output, snapshot)

    def retry(self, job_id, expected_attempt=None):
        require(job_id not in self.tasks, 'This recipe step is still running.', 409)
        with self.database.connect(write=True) as connection:
            job = one(connection, 'SELECT * FROM recipe_jobs WHERE id=?', (job_id,))
            require(expected_attempt is None or job['attempt'] == expected_attempt, 'Another view changed this recipe attempt. Review its current state.', 409)
            require(job['status'] in {'error', 'cancelled', 'interrupted'}, 'Retry only an unfinished request.', 409)
            require_current_ceiling(connection, decode(job['snapshot']))
            preserve_attempt(connection, job_id, self.prefix)
            connection.execute("UPDATE recipe_jobs SET status='queued',output='',result='null',usage='{}',error='' WHERE id=?", (job_id,))
        self.start(job_id)
        return {'retried': True}

    def cancel(self, job_id, expected_attempt=None):
        with self.database.connect() as connection:
            job = one(connection, 'SELECT attempt,status FROM recipe_jobs WHERE id=?', (job_id,))
            attempt = job['attempt'] + (1 if job['status'] == 'queued' else 0)
            require(expected_attempt is None or attempt == expected_attempt, 'Another view started a newer recipe attempt. Review it before stopping.', 409)
        return super().cancel(job_id)

    async def consume(self, job_id, snapshot, state):
        # Persist the first chunk even when the provider then stalls indefinitely.
        completion, saved = StreamCompletion(), 0.0
        async with aclosing(self.provider.generate(snapshot['profile'], snapshot['instructions'], snapshot['content'])) as stream:
            async for event in stream:
                completion.observe(event)
                state['output'] += event.text
                state['usage'].update(event.usage)
                state['usage']['completion'] = asdict(completion)
                if event.model:
                    state['usage']['actual_model'] = event.model
                require(len(state['output']) <= 200000, 'This recipe step exceeded its response limit. No text was applied.', 502)
                if time.monotonic() - saved > .15:
                    self.save(job_id, state)
                    saved = time.monotonic()
        completion.validate(snapshot['profile']['config'])

    def save(self, job_id, state, final=False):
        with self.database.connect(write=True) as connection:
            job = one(connection, 'SELECT * FROM recipe_jobs WHERE id=?', (job_id,))
            if final and state['status'] == 'done':
                check_replacement(connection, job, state)
            connection.execute('UPDATE recipe_jobs SET status=?,output=?,result=?,usage=?,error=?,updated_at=? WHERE id=?',
                (state['status'], state['output'], encode(state['result']), encode(state['usage']), state['error'], now(), job_id))
            if final:
                finish_recipe(connection, job['run_id'])
                preserve_attempt(connection, job_id, self.prefix)


def check_replacement(connection, job, state):
    if decode(job['snapshot'])['task'] == 'review':
        return
    run = read_run(connection, job['run_id'])
    try:
        proposed_text({'target': run['target'], 'selection': run['snapshot']['selection'],
                       'action': run['snapshot']['action'], 'replacement': state['result']['replacement']})
    except DomainError as error:
        state.update(status='error', result=None, error=error.message)
