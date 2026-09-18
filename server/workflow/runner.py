import asyncio
import json
import time

from pydantic import ValidationError

from server.agent_switches import require_agent
from server.database import decode, encode, identifier, now, one
from server.errors import DomainError, require
from server.memory.source_evidence import quotation_matches
from server.prompt_sections import system_prompt
from server.workflow.models import ReviewOutput
from server.workflow.readers import coverage_report, validate_reader


def parse_review(output, content):
    context = decode(content)
    try:
        data = json.loads(output)
        if context.get('reader_contract') == 'coverage-v1':
            data = coverage_report(data, context)
        result = ReviewOutput.model_validate(data)
    except (ValueError, ValidationError) as error:
        raise DomainError("The reviewer did not return the required structured report. Its text is preserved; check the role prompt or retry.", 502) from error
    validate_reader(result, context)
    sources = {source["id"]: source for source in context["sources"]}
    for finding in result.findings:
        require(finding.source_id in sources, "The reviewer cited a source outside its permitted inputs. The report is not validated.", 502)
        require(quotation_matches(sources[finding.source_id], finding.quote), "A review quotation does not match its cited source. The report is not validated.", 502)
    return result.model_dump()


def preserve_attempt(connection, job_id, prefix="review"):
    job = one(connection, f"SELECT * FROM {prefix}_jobs WHERE id=?", (job_id,))
    connection.execute(f"INSERT OR IGNORE INTO {prefix}_attempts VALUES (?,?,?,?,?,?,?,?,?)",
                       (identifier(), job_id, job["attempt"], job["status"], job["output"], job["result"], job["usage"],
                        job["error"], now()))


class ReviewRunner:
    prefix = "review"
    label = "review"

    def __init__(self, database, provider):
        self.database = database
        self.provider = provider
        self.tasks = {}

    def recover(self):
        with self.database.connect(write=True) as connection:
            connection.execute(f"UPDATE {self.prefix}_jobs SET status='interrupted',error=? WHERE status IN ('queued','running')",
                               (f"The application stopped. Partial {self.label} text is preserved; retry is explicit.",))

    def start(self, job_id):
        if job_id in self.tasks:
            return
        task = asyncio.create_task(self.run(job_id))
        self.tasks[job_id] = task
        task.add_done_callback(lambda _task: self.tasks.pop(job_id, None))

    def claim(self, job_id):
        with self.database.connect(write=True) as connection:
            job = one(connection, f"SELECT * FROM {self.prefix}_jobs WHERE id=?", (job_id,))
            if job["status"] != "queued":
                return None
            connection.execute(f"UPDATE {self.prefix}_jobs SET status='running',attempt=attempt+1 WHERE id=?", (job_id,))
            return decode(job["snapshot"])

    async def run(self, job_id):
        snapshot = self.claim(job_id)
        if snapshot is None:
            return
        state = {"status": "running", "output": "", "result": None, "usage": {}, "error": ""}
        try:
            await self.consume(job_id, snapshot, state)
            state.update(status="done", result=self.parse_result(state["output"], snapshot))
        except asyncio.CancelledError:
            state.update(status="cancelled", error=f"Stopped. Partial {self.label} text is preserved.")
        except DomainError as error:
            state.update(status="error", error=error.message)
        except Exception:
            state.update(status="error", error=f"The {self.label} could not complete. The story is unchanged.")
        finally:
            self.save(job_id, state, final=True)

    def parse_result(self, output, snapshot):
        if snapshot.get('purpose') == 'planned-continuity-v1':
            from server.memory.plan_scan_output import parse_plan_scan
            return parse_plan_scan(output, snapshot)
        return parse_review(output, snapshot["content"])

    async def consume(self, job_id, snapshot, state):
        saved = time.monotonic()
        async for event in self.provider.generate(snapshot["profile"], system_prompt(snapshot), snapshot["content"]):
            state["output"] += event.text
            state["usage"].update(event.usage)
            if event.model:
                state["usage"]["actual_model"] = event.model
            if time.monotonic() - saved > 0.15:
                self.save(job_id, state)
                saved = time.monotonic()

    def save(self, job_id, state, final=False):
        with self.database.connect(write=True) as connection:
            connection.execute(f"UPDATE {self.prefix}_jobs SET status=?,output=?,result=?,usage=?,error=?,updated_at=? WHERE id=?",
                               (state["status"], state["output"], encode(state["result"]), encode(state["usage"]), state["error"], now(), job_id))
            if final:
                preserve_attempt(connection, job_id, self.prefix)

    def cancel(self, job_id):
        with self.database.connect(write=True) as connection:
            job = one(connection, f"SELECT * FROM {self.prefix}_jobs WHERE id=?", (job_id,))
            if job["status"] == "queued":
                connection.execute(f"UPDATE {self.prefix}_jobs SET status='cancelled',error='Stopped before generation.' WHERE id=?", (job_id,))
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
        return {"stopped": True}

    def retry(self, job_id):
        require(job_id not in self.tasks, "This specialist is still running.", 409)
        with self.database.connect(write=True) as connection:
            job = one(connection, f"SELECT * FROM {self.prefix}_jobs WHERE id=?", (job_id,))
            require(job["status"] in {"error", "cancelled", "interrupted"}, "Retry only an unfinished request.", 409)
            require_retry_enabled(connection, job)
            preserve_attempt(connection, job_id, self.prefix)
            connection.execute(f"UPDATE {self.prefix}_jobs SET status='queued',output='',result='null',usage='{{}}',error='' WHERE id=?", (job_id,))
        self.start(job_id)
        return {"retried": True}

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def require_retry_enabled(connection, job):
    snapshot = decode(job['snapshot'])
    story = None
    if snapshot.get('purpose') == 'planned-continuity-v1':
        story = one(connection, 'SELECT s.* FROM stories s JOIN branches b ON b.story_id=s.id '
                    'JOIN review_runs r ON r.branch_id=b.id WHERE r.id=?', (job['run_id'],))
    require_agent(connection, job['step'], story)
