import asyncio
import time

from server.agent_switches import require_agent
from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.generation_activity import interrupt_activity, save_activity, start_activity
from server.operations import previous, remember
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

    def recover(self):
        with self.database.connect(write=True) as connection:
            interrupt_activity(connection)
            connection.execute("UPDATE candidates SET status='interrupted', error=? WHERE status IN ('running','queued')",
                               ("The application stopped before this draft completed. Retry explicitly to continue.",))

    def start(self, candidate_id):
        if candidate_id in self.tasks:
            return
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
        claimed = self.claim(candidate_id)
        if claimed is None:
            return
        candidate, snapshot = claimed
        state = {"output": "", "usage": {}, "error": "", "status": "running"}
        try:
            await self._consume(candidate, snapshot, state)
            if not state['output'].strip():
                raise DomainError('The provider returned no story text.', 502, 'empty_response')
            state["status"] = "done"
        except asyncio.CancelledError:
            state.update(status="cancelled", error="Stopped. Partial text is preserved.", error_kind='cancelled')
        except DomainError as error:
            state.update(status="error", error=error.message, error_kind=error.code)
        except Exception:
            state.update(status="error", error="An unexpected provider error occurred. Your story was not changed.", error_kind='provider')
        finally:
            self.save(candidate_id, state, final=True)

    async def _consume(self, candidate, snapshot, state):
        profile = decode(candidate["profile"])
        last_save = time.monotonic()
        async for event in self.provider.generate(profile, snapshot["prompt"]["template"], snapshot["content"]):
            first_text = bool(event.text) and not state['output']
            state['last_event_at'] = now()
            if first_text:
                state['first_text_at'] = now()
            state["output"] += event.text
            state["usage"].update(event.usage)
            if event.model:
                state["usage"]["actual_model"] = event.model
            if first_text or time.monotonic() - last_save > 0.15:
                self.save(candidate["id"], state)
                last_save = time.monotonic()

    def save(self, candidate_id, state, final=False):
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE candidates SET output=?,usage=?,status=?,error=?,updated_at=? WHERE id=?",
                               (state["output"], encode(state["usage"]), state["status"], state["error"], now(), candidate_id))
            save_activity(connection, candidate_id, state, final)
            if final:
                preserve_attempt(connection, candidate_id)

    def cancel(self, candidate_id):
        with self.database.connect(write=True) as connection:
            candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            if candidate['status'] not in {'queued', 'running'}:
                return {'stopped': False, 'status': candidate['status']}
            if candidate["status"] == "queued":
                connection.execute("UPDATE candidates SET status='cancelled',error='Stopped before generation.' WHERE id=?", (candidate_id,))
        task = self.tasks.get(candidate_id)
        if task:
            task.cancel()
        return {"stopped": True}

    def retry(self, candidate_id, body=None):
        payload = {'candidate_id': candidate_id, **(body.model_dump() if body else {})}
        with self.database.connect(write=True) as connection:
            if body:
                cached = previous(connection, body.operation_id, 'retry_candidate', payload)
                if cached is not None:
                    return cached
            require(candidate_id not in self.tasks, "This draft is still running.", 409)
            require_agent(connection, "writer")
            candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            require(body is None or body.expected_attempt == candidate['attempt'], 'This attempt changed. Refresh the draft before retrying.', 409)
            require(candidate["status"] in {"error", "cancelled", "interrupted"}, "Only an unfinished draft can be retried.", 409)
            preserve_attempt(connection, candidate_id)
            connection.execute("UPDATE candidates SET status='queued',output='',usage='{}',error='' WHERE id=?", (candidate_id,))
            if body:
                remember(connection, body.operation_id, 'retry_candidate', payload, {'retried': True})
        self.start(candidate_id)
        return {"retried": True}

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def pending(self, generation_id):
        with self.database.connect() as connection:
            return many(connection, "SELECT id FROM candidates WHERE generation_id=? AND status='queued'", (generation_id,))
