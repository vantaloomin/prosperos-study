"""One durable maintenance dispatcher; requests run in sequence with explicit recovery."""
import asyncio
from datetime import UTC, datetime, timedelta

from starlette.concurrency import run_in_threadpool

from server.database import now, one
from server.errors import DomainError, require
from server.memory.maintenance_service import (
    automatic_plan,
    record_automatic,
    require_batch_enabled,
)
from server.memory.maintenance_storage import batch_jobs, set_batch_status
from server.operations import previous, remember
from server.workflow.runner import preserve_attempt


class MaintenanceRunner:
    def __init__(self, database, summaries):
        self.database, self.summaries = database, summaries
        self.task = None
        self.debounce_seconds = 2

    def recover(self):
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE summary_batches SET status='interrupted',error='The app stopped. Resume is explicit.' WHERE status IN ('queued','running')")
            connection.execute("UPDATE summary_wakeups SET status='interrupted',revision=revision+1,error='The app stopped. Resume waiting maintenance explicitly.' WHERE status='pending'")

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self.loop())

    async def shutdown(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def next_work(self):
        threshold = (datetime.now(UTC) - timedelta(seconds=self.debounce_seconds)).isoformat()
        with self.database.connect() as connection:
            queued = connection.execute("SELECT id FROM summary_batches WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if queued:
                return 'batch', dict(queued)
            wake = connection.execute("SELECT * FROM summary_wakeups WHERE status='pending' AND allowance>0 AND updated_at<=? ORDER BY updated_at LIMIT 1", (threshold,)).fetchone()
            return ('automatic', dict(wake)) if wake else (None, None)

    async def loop(self):
        while True:
            kind, work = await run_in_threadpool(self.next_work)
            if kind == 'batch':
                await self.run_batch(work['id'])
            elif kind == 'automatic':
                await self.prepare_automatic(work)
            await asyncio.sleep(0.25)

    async def prepare_automatic(self, wake):
        try:
            prepared = await run_in_threadpool(automatic_plan, self.database, wake['branch_id'])
        except DomainError as error:
            with self.database.connect(write=True) as connection:
                connection.execute("UPDATE summary_wakeups SET status='error',error=?,revision=revision+1 WHERE id=? AND revision=?",
                                   (error.message, wake['id'], wake['revision']))
            return
        except Exception:
            with self.database.connect(write=True) as connection:
                connection.execute("UPDATE summary_wakeups SET status='error',error=?,revision=revision+1 WHERE id=? AND revision=?",
                    ('Summary preparation could not complete. Accepted text is preserved; review settings and resume explicitly.', wake['id'], wake['revision']))
            return
        try:
            await run_in_threadpool(record_automatic, self.database, prepared)
        except DomainError:
            # A concurrent acceptance/configuration/request changed the read snapshot.
            # Replan next time; nothing was recorded or dispatched by the failed write.
            return

    def claim(self, batch_id):
        with self.database.connect(write=True) as connection:
            row = one(connection, 'SELECT * FROM summary_batches WHERE id=?', (batch_id,))
            if row['status'] != 'queued':
                return None
            set_batch_status(connection, batch_id, 'running')
            return row

    async def run_batch(self, batch_id):
        batch = await run_in_threadpool(self.claim, batch_id)
        if batch is None:
            return
        try:
            with self.database.connect() as connection:
                jobs = batch_jobs(connection, batch_id)
            for job in jobs:
                if not self.ready_job(batch, job['id']):
                    return
                with self.database.connect() as connection:
                    status = one(connection, 'SELECT status FROM summary_jobs WHERE id=?', (job['id'],))['status']
                if status != 'done':
                    self.summaries.start(job['id'])
                    await asyncio.shield(self.summaries.tasks[job['id']])
                if not self.check_finished(batch, job['id']):
                    return
            self.finish(batch, 'done')
        except asyncio.CancelledError:
            self.cancel_children(batch_id)
            self.finish(batch, 'interrupted', 'The app stopped. Partial output is preserved; resume explicitly.')
            raise
        except Exception:
            self.finish(batch, 'error', 'Summary maintenance could not continue. Saved inputs remain available; resume explicitly.')

    def ready_job(self, batch, job_id):
        with self.database.connect(write=True) as connection:
            if one(connection, 'SELECT status FROM summary_batches WHERE id=?', (batch['id'],))['status'] != 'running':
                return False
            try:
                require_batch_enabled(connection, batch)
            except DomainError as error:
                set_batch_status(connection, batch['id'], 'paused', error.message)
                return False
            status = one(connection, 'SELECT status FROM summary_jobs WHERE id=?', (job_id,))['status']
            if status not in {'queued', 'done'}:
                set_batch_status(connection, batch['id'], 'error', 'A saved request needs attention. Resume the batch explicitly.')
                return False
            return True

    def check_finished(self, batch, job_id):
        with self.database.connect() as connection:
            job = one(connection, 'SELECT status,error FROM summary_jobs WHERE id=?', (job_id,))
        if job['status'] == 'done':
            return True
        self.finish(batch, 'error', job['error'] or 'A summary request did not complete. Resume is explicit.')
        return False

    def finish(self, batch, status, error=''):
        with self.database.connect(write=True) as connection:
            current = one(connection, 'SELECT status FROM summary_batches WHERE id=?', (batch['id'],))['status']
            if current != 'running':
                return
            set_batch_status(connection, batch['id'], status, error)
            if batch['kind'] == 'automatic' and status == 'done':
                connection.execute("UPDATE summary_wakeups SET status=CASE WHEN EXISTS "
                    "(SELECT 1 FROM summary_pending WHERE branch_id=summary_wakeups.branch_id) THEN 'limited' ELSE 'idle' END,"
                    "error='',revision=revision+1 WHERE branch_id=? AND status IN ('error','interrupted','paused')", (batch['branch_id'],))
            if batch['kind'] == 'automatic' and status in {'error', 'interrupted'}:
                connection.execute('UPDATE summary_wakeups SET status=?,error=?,revision=revision+1 WHERE branch_id=?',
                                   (status, error, batch['branch_id']))

    def cancel_children(self, batch_id):
        with self.database.connect() as connection:
            jobs = batch_jobs(connection, batch_id)
        for job in jobs:
            if job['id'] in self.summaries.tasks:
                self.summaries.tasks[job['id']].cancel()

    def stop(self, batch_id):
        with self.database.connect(write=True) as connection:
            batch = one(connection, 'SELECT * FROM summary_batches WHERE id=?', (batch_id,))
            if batch['status'] == 'done':
                return {'stopped': False}
            set_batch_status(connection, batch_id, 'cancelled', 'Stopped. No further requests will be started.')
            connection.execute("UPDATE summary_jobs SET status='cancelled',error='Stopped before dispatch.' WHERE status='queued' "
                               'AND run_id IN (SELECT run_id FROM summary_batch_runs WHERE batch_id=?)', (batch_id,))
            if batch['kind'] == 'automatic':
                connection.execute("UPDATE summary_wakeups SET status='paused',revision=revision+1 WHERE branch_id=?", (batch['branch_id'],))
        self.cancel_children(batch_id)
        return {'stopped': True}

    def resume(self, batch_id, body):
        payload = {'batch_id': batch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'summary-batch-resume', payload)
            if cached is not None:
                return cached
            batch = one(connection, 'SELECT * FROM summary_batches WHERE id=?', (batch_id,))
            require(batch['status'] == body.expected_status and batch['status'] in {'paused', 'error', 'cancelled', 'interrupted'},
                    'This batch changed. Refresh before resuming.', 409)
            require_batch_enabled(connection, batch)
            jobs = batch_jobs(connection, batch_id)
            require(not any(job['id'] in self.summaries.tasks for job in jobs), 'A request is still stopping. Wait before resuming.', 409)
            reset_unfinished(connection, jobs)
            set_batch_status(connection, batch_id, 'queued')
            return remember(connection, body.operation_id, 'summary-batch-resume', payload, {'resumed': True})


def reset_unfinished(connection, jobs):
    for job in jobs:
        if job['status'] == 'done':
            continue
        preserve_attempt(connection, job['id'], 'summary')
        connection.execute("UPDATE summary_jobs SET status='queued',output='',result='null',usage='{}',error='',updated_at=? WHERE id=?", (now(), job['id']))
