import asyncio
import time
from datetime import datetime

from server.agent_switches import require_agent
from server.cleanup import runner as cleanup_runner
from server.cleanup.storage import permitted
from server.continuity_revision import prepare as prepare_revision
from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.generation_activity import interrupt_activity, save_activity, start_activity
from server.memory.writer_recall_runner import prepare as prepare_recall
from server.memory.writer_recall_runner import reusable
from server.operations import previous, remember
from server.prompt_sections import system_prompt
from server.providers.scheduling import WRITING, work_scope
from server.providers.service import ProviderService


def preserve_attempt(connection, candidate_id):
    candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
    exists = connection.execute("SELECT 1 FROM generation_attempts WHERE candidate_id=? AND attempt=?",
                                (candidate_id, candidate["attempt"])).fetchone()
    if exists:
        return
    connection.execute("INSERT INTO generation_attempts VALUES (?,?,?,?,?,?,?,?)",
                       (identifier(), candidate_id, candidate["attempt"], candidate["status"], candidate["output"],
                        candidate["usage"], candidate["error"], now()))


class GenerationRunner:
    def __init__(self, database, vault):
        self.database = database
        self.provider = ProviderService(vault, database=database)
        self.tasks = {}
        self.cleanup_tasks = {}

    def recover(self):
        with self.database.connect(write=True) as connection:
            for row in cleanup_runner.recover(connection):
                preserve_attempt(connection, row['candidate_id'])
            interrupt_activity(connection)
            connection.execute("UPDATE candidates SET status='interrupted', error=? WHERE status IN ('running','queued')",
                               ("The application stopped before this draft completed. Retry explicitly to continue.",))

    def start(self, candidate_id):
        if candidate_id in self.tasks:
            return
        with self.database.connect() as connection:
            target = one(connection, 'SELECT g.branch_id,g.id AS generation_id,c.status FROM candidates c '
                         'JOIN generations g ON g.id=c.generation_id WHERE c.id=?', (candidate_id,))
        if target['status'] == 'queued':
            self.yield_branch_cleanup(target['branch_id'], target['generation_id'])
        task = asyncio.create_task(self._run(candidate_id))
        self.tasks[candidate_id] = task
        task.add_done_callback(lambda _task: self.tasks.pop(candidate_id, None))

    def claim(self, candidate_id):
        with self.database.connect(write=True) as connection:
            candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            if candidate["status"] != "queued":
                return None
            connection.execute("UPDATE candidates SET status='running',attempt=attempt+1 WHERE id=?", (candidate_id,))
            start_activity(connection, candidate_id, candidate['attempt'] + 1)
            generation = one(connection, "SELECT * FROM generations WHERE id=?", (candidate["generation_id"],))
            return candidate, decode(generation["snapshot"])

    async def _run(self, candidate_id):
        with work_scope(WRITING):
            await self._write(candidate_id)

    async def _write(self, candidate_id):
        claimed = self.claim(candidate_id)
        if claimed is None:
            return
        candidate, snapshot = claimed
        started = time.monotonic()
        saved_usage = reusable(decode(candidate['usage']))
        timings = ({'request_received_at': candidate['updated_at']} if 'continuity_revision' in saved_usage
                   else dict(snapshot.get('timings', {})))
        state = {"output": "", "usage": {**saved_usage, 'timings': timings}, "error": "", "status": "running"}
        try:
            snapshot = await prepare_recall(self.provider, candidate, snapshot, state, self.save)
            snapshot = prepare_revision(candidate, snapshot, state)
            writer_started = time.monotonic()
            await self._consume(candidate, snapshot, state)
            if not state['output'].strip():
                raise DomainError('The provider returned no story text.', 502, 'empty_response')
            state['writer_complete'] = True
            state['usage']['timings']['writer_seconds'] = time.monotonic() - writer_started
            if snapshot.get('cleanup', {}).get('timing') == 'reading':
                state['usage']['cleanup_pending'] = True
                self.start_cleanup(candidate_id, snapshot)
            # Persist the complete original before starting any optional polishing.
            state['status'] = 'cleaning' if snapshot.get('cleanup') and not state['usage'].get('cleanup_pending') else 'done'
            self.save(candidate_id, state)
            if state['status'] == 'cleaning':
                await cleanup_runner.run(self.database, self.provider, candidate_id, snapshot)
            state["status"] = "done"
        except asyncio.CancelledError:
            state.update(status="cancelled", error="Stopped. Partial text is preserved.", error_kind='cancelled')
        except DomainError as error:
            state.update(status="error", error=error.message, error_kind=error.code)
        except Exception:
            state.update(status="error", error="An unexpected provider error occurred. Your story was not changed.", error_kind='provider')
        finally:
            if state.get('writer_complete'):
                state.update(status='done', error=('Cleanup stopped before completion. The original draft is available.' if state['error'] else ''))
                state['usage']['timings']['draft_ready_seconds'] = time.monotonic() - started
            self.save(candidate_id, state, final=True)

    def start_cleanup(self, candidate_id, snapshot):
        task = asyncio.create_task(self.background_cleanup(candidate_id, snapshot))
        self.cleanup_tasks[candidate_id] = task
        task.add_done_callback(lambda _: self.cleanup_tasks.pop(candidate_id, None))

    async def background_cleanup(self, candidate_id, snapshot):
        try:
            await cleanup_runner.run(self.database, self.provider, candidate_id, snapshot)
        finally:
            with self.database.connect(write=True) as connection:
                connection.execute("UPDATE candidates SET usage=json_set(usage,'$.cleanup_pending',json('false')) WHERE id=?", (candidate_id,))

    async def _consume(self, candidate, snapshot, state):
        profile = decode(candidate["profile"])
        last_save = time.monotonic()
        async for event in self.provider.generate(profile, system_prompt(snapshot), snapshot["content"]):
            first_text = bool(event.text) and not state['output']
            state['last_event_at'] = now()
            if first_text:
                state['first_text_at'] = now()
                received = state['usage'].get('timings', {}).get('request_received_at')
                if received and candidate['attempt'] == 0:
                    state['usage']['timings']['request_to_first_text_seconds'] = max(0, (datetime.fromisoformat(state['first_text_at']) - datetime.fromisoformat(received)).total_seconds())
            state["output"] += event.text
            state["usage"].update(event.usage)
            if event.model:
                state["usage"]["actual_model"] = event.model
            if first_text or time.monotonic() - last_save > 0.15:
                self.save(candidate["id"], state)
                last_save = time.monotonic()

    def save(self, candidate_id, state, final=False):
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE candidates SET output=CASE WHEN ? THEN output ELSE ? END,usage=?,status=?,error=?,updated_at=? WHERE id=?",
                               (final and state.get('writer_complete', False), state["output"], encode(state["usage"]),
                                state["status"], state["error"], now(), candidate_id))
            save_activity(connection, candidate_id, state, final)
            if final:
                preserve_attempt(connection, candidate_id)

    def cancel(self, candidate_id):
        if candidate_id in self.cleanup_tasks:
            return self.stop_background_cleanup(candidate_id)
        with self.database.connect(write=True) as connection:
            candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            if candidate['status'] not in {'queued', 'running', 'cleaning'}:
                return {'stopped': False, 'status': candidate['status']}
            if candidate["status"] == "queued":
                connection.execute("UPDATE candidates SET status='cancelled',error='Stopped before generation.' WHERE id=?", (candidate_id,))
            if candidate['status'] == 'cleaning':
                connection.execute("UPDATE candidate_cleanups SET status='cancelled',selected='original',error=?,updated_at=? "
                                   "WHERE candidate_id=? AND attempt=? AND status='running'",
                                   ('Cleanup stopped. The original draft is available.', now(), candidate_id, candidate['attempt']))
                connection.execute("UPDATE candidates SET status='done',error='' WHERE id=?", (candidate_id,))
                connection.execute("UPDATE candidate_activity SET finished_at=?,error_kind='cleanup_cancelled' WHERE candidate_id=? AND attempt=?",
                                   (now(), candidate_id, candidate['attempt']))
                preserve_attempt(connection, candidate_id)
        task = self.tasks.get(candidate_id)
        if task:
            task.cancel()
        return {"stopped": True}

    def stop_background_cleanup(self, candidate_id):
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE candidates SET usage=json_set(usage,'$.cleanup_pending',json('false')) WHERE id=?", (candidate_id,))
            connection.execute("UPDATE candidate_cleanups SET status='cancelled',selected='original',error=?,updated_at=? "
                               "WHERE candidate_id=? AND status='running'",
                               ('Cleanup stopped. The original draft is available.', now(), candidate_id))
        task = self.cleanup_tasks.get(candidate_id)
        if task and not task.cancelling():
            task.cancel()
        return {'stopped': bool(task)}

    def retry(self, candidate_id, body=None):
        payload = {'candidate_id': candidate_id, **(body.model_dump() if body else {})}
        with self.database.connect(write=True) as connection:
            if body:
                cached = previous(connection, body.operation_id, 'retry_candidate', payload)
                if cached is not None:
                    return cached
            require(candidate_id not in self.tasks, "This draft is still running.", 409)
            candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            story = one(connection, 'SELECT s.* FROM stories s JOIN branches b ON b.story_id=s.id '
                        'JOIN generations g ON g.branch_id=b.id WHERE g.id=?', (candidate['generation_id'],))
            require_agent(connection, 'writer', story)
            require(body is None or body.expected_attempt == candidate['attempt'], 'This attempt changed. Refresh the draft before retrying.', 409)
            require(candidate["status"] in {"error", "cancelled", "interrupted"}, "Only an unfinished draft can be retried.", 409)
            preserve_attempt(connection, candidate_id)
            connection.execute("UPDATE candidates SET status='queued',output='',usage=?,error='' WHERE id=?",
                               (encode(reusable(decode(candidate['usage']))), candidate_id))
            if body:
                remember(connection, body.operation_id, 'retry_candidate', payload, {'retried': True})
        self.start(candidate_id)
        return {"retried": True}

    def cancel_cleanup(self, branch_id):
        with self.database.connect() as connection:
            rows = many(connection, "SELECT candidate_id,snapshot FROM candidate_cleanups WHERE branch_id=? AND status='running'", (branch_id,))
            obsolete = [row['candidate_id'] for row in rows if not permitted(connection, decode(row['snapshot']))]
        for candidate_id in obsolete:
            self.cancel(candidate_id)

    def yield_branch_cleanup(self, branch_id, generation_id):
        with self.database.connect() as connection:
            rows = many(connection, 'SELECT c.id FROM candidates c JOIN generations g ON g.id=c.generation_id '
                        "WHERE g.branch_id=? AND g.id!=? AND json_extract(c.usage,'$.cleanup_pending')=1", (branch_id, generation_id))
        for row in rows:
            self.stop_background_cleanup(row['id'])

    async def shutdown(self):
        tasks = [*self.tasks.values(), *self.cleanup_tasks.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def pending(self, generation_id):
        with self.database.connect() as connection:
            return many(connection, "SELECT id FROM candidates WHERE generation_id=? AND status='queued'", (generation_id,))
