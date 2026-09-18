import asyncio
import json
import time

from starlette.concurrency import run_in_threadpool

from server.agent_switches import require_agent
from server.database import decode, encode, many, now, one
from server.errors import DomainError, require
from server.memory.side_packet import next_packet, request_receipt
from server.memory.side_search import SourceArchive, command
from server.side_context import assemble_context
from server.side_conversations import SideConversations


def requested_sources(output, allowed):
    if not output.lstrip().startswith("READ_SOURCES:"):
        return None
    try:
        ids = json.loads(output.strip()[13:].strip())
    except ValueError as error:
        raise DomainError("The collaborator returned an unreadable source request. The story is unchanged.", 502) from error
    require(isinstance(ids, list) and 0 < len(ids) <= 8, "A source request must name 1–8 archived passages.", 502)
    require(all(isinstance(item, str) and item in allowed for item in ids),
            "The collaborator requested a source outside this frozen archive. No operation was performed.", 502)
    return ids


class SideRunner:
    def __init__(self, database, provider):
        self.database = database
        self.provider = provider
        self.tasks = {}

    def recover(self):
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE side_replies SET status='interrupted',error=? WHERE status IN ('queued','running')",
                               ("The application stopped. The partial reply is preserved; retry is explicit.",))

    def start(self, reply_id):
        if reply_id in self.tasks:
            return
        task = asyncio.create_task(self.run(reply_id))
        self.tasks[reply_id] = task
        task.add_done_callback(lambda _task: self.tasks.pop(reply_id, None))

    def claim(self, reply_id):
        with self.database.connect(write=True) as connection:
            reply = one(connection, "SELECT * FROM side_replies WHERE id=?", (reply_id,))
            if reply["status"] != "queued":
                return None
            connection.execute("UPDATE side_replies SET status='running' WHERE id=?", (reply_id,))
            turn = one(connection, "SELECT * FROM side_turns WHERE id=?", (reply["turn_id"],))
            return decode(reply["profile"]), decode(turn["snapshot"])

    async def run(self, reply_id):
        claimed = self.claim(reply_id)
        if claimed is None:
            return
        state = {"status": "running", "output": "", "error": "", "usage": [], "coverage": []}
        try:
            await self.answer(reply_id, *claimed, state)
            state["status"] = "done"
        except asyncio.CancelledError:
            state.update(status="cancelled", error="Stopped. Any partial reply is preserved.")
        except DomainError as error:
            state.update(status="error", error=error.message)
        except Exception:
            state.update(status="error", error="The collaborator could not complete this reply. The story is unchanged.")
        finally:
            self.save(reply_id, state)

    async def answer(self, reply_id, profile, snapshot, state):
        if snapshot.get('retrieval'):
            return await self.search_answer(reply_id, profile, snapshot, state)
        source_ids = snapshot["initial_source_ids"]
        allowed = {item["id"] for item in snapshot["sources"]}
        for read in range(snapshot["max_reads"] + 1):
            content = assemble_context(snapshot, profile, source_ids)
            state["coverage"] = sorted(set(state["coverage"]) | set(source_ids))
            output = await self.request(reply_id, profile, snapshot["prompt"]["template"], content, state)
            requested = requested_sources(output, allowed)
            if requested is None:
                require(bool(output.strip()), "The collaborator returned no answer.", 502)
                state["output"] = output
                return
            require(read < snapshot["max_reads"], "The source-reading limit was reached. Inspect the coverage and ask a narrower question or increase the limit.", 409)
            source_ids = list(dict.fromkeys([*source_ids, *requested]))
            state["output"] = ""

    async def search_answer(self, reply_id, profile, snapshot, state):
        archive = SourceArchive(snapshot)
        content = snapshot['retrieval']['initial_content']
        for read in range(snapshot['max_reads'] + 1):
            output = await self.request(reply_id, profile, snapshot['prompt']['template'], content, state)
            requested = command(output)
            if requested is None:
                require(bool(output.strip()), 'The collaborator returned no answer.', 502)
                state['output'] = output
                return
            require(read < snapshot['max_reads'], 'The archive-reading limit was reached. Inspect coverage, ask a narrower question or increase the limit.', 409)
            content = await run_in_threadpool(next_packet, snapshot, archive, requested)
            state['output'] = ""

    async def request(self, reply_id, profile, prompt, content, state):
        output = ""
        context = decode(content)
        usage = request_receipt(content) if context.get('retrieval_protocol') else {
            "source_ids": [source["id"] for source in context["sources"]], "reported": {}}
        state["coverage"] = sorted(set(state["coverage"]) | set(usage["source_ids"]))
        state["usage"].append(usage)
        saved = time.monotonic()
        async for event in self.provider.generate(profile, prompt, content):
            output += event.text
            if 'content' in usage:
                usage['output'] = output
            usage["reported"].update(event.usage)
            if event.model:
                usage["reported"]["actual_model"] = event.model
            state["output"] = output
            if time.monotonic() - saved > 0.15:
                self.save(reply_id, state)
                saved = time.monotonic()
        return output

    def save(self, reply_id, state):
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE side_replies SET status=?,output=?,error=?,usage=?,coverage=?,updated_at=? WHERE id=?",
                               (state["status"], state["output"], state["error"], encode(state["usage"]),
                                encode(state["coverage"]), now(), reply_id))

    def cancel(self, reply_id):
        with self.database.connect(write=True) as connection:
            reply = one(connection, "SELECT * FROM side_replies WHERE id=?", (reply_id,))
            if reply["status"] == "queued":
                connection.execute("UPDATE side_replies SET status='cancelled' WHERE id=?", (reply_id,))
        task = self.tasks.get(reply_id)
        if task:
            task.cancel()
        return {"stopped": True}

    def retry(self, reply_id):
        require(reply_id not in self.tasks, "This reply is still running.", 409)
        with self.database.connect(write=True) as connection:
            require_agent(connection, "collaborator")
            reply = one(connection, "SELECT * FROM side_replies WHERE id=?", (reply_id,))
            require(reply["status"] in {"error", "cancelled", "interrupted"}, "Retry only an unfinished reply.", 409)
            pending = connection.execute("SELECT 1 FROM side_replies WHERE turn_id=? AND status IN ('queued','running')",
                                         (reply["turn_id"],)).fetchone()
            require(pending is None, "Wait for the other replies or stop them before retrying.", 409)
            replacement = SideConversations.new_reply(connection, reply["turn_id"], decode(reply["profile"]))
            connection.execute("UPDATE side_turns SET selected_reply_id=? WHERE id=? AND selected_reply_id=?",
                               (replacement, reply["turn_id"], reply_id))
        self.start(replacement)
        return {"reply_id": replacement}

    def pending(self, turn_id):
        with self.database.connect() as connection:
            return many(connection, "SELECT id FROM side_replies WHERE turn_id=? AND status='queued'", (turn_id,))

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
