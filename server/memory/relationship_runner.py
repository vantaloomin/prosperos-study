"""Durable incremental extraction; model interpretations never accept story state."""
import asyncio
import time
from collections import OrderedDict
from contextlib import aclosing

from server.agent_switches import require_agent
from server.branches import path_nodes
from server.database import decode, encode, many, now, one
from server.errors import DomainError, require
from server.memory.relationship_context import extraction_profile, plan_requests
from server.memory.relationship_output import MAX_OUTPUT, parse_annotations
from server.memory.relationship_sources import job_sources, source_catalog, story_policy
from server.memory.relationship_storage import insert_jobs
from server.providers.scheduling import BackgroundInterrupted, Work, work_scope
from server.workflow.runner import preserve_attempt


class RelationshipRunner:
    def __init__(self, database, provider):
        self.database, self.provider = database, provider
        self.tasks, self.automatic_tasks = {}, set()
        self.loop = None
        self.watcher = None
        self.pending_nodes = OrderedDict()
        self.dispatcher = None

    def recover(self):
        with self.database.connect(write=True) as connection:
            for row in many(connection, "SELECT id FROM relationship_jobs WHERE status IN ('queued','running')"):
                connection.execute("UPDATE relationship_jobs SET status='interrupted',error='The app stopped. Retry explicitly.' WHERE id=?", (row['id'],))
                preserve_attempt(connection, row['id'], 'relationship')

    def start(self):
        self.loop = asyncio.get_running_loop()
        self.database.node_listeners.append(self.changed)
        self.watcher = asyncio.create_task(self.watch())

    def changed(self, nodes):
        if self.loop and not self.loop.is_closed():
            # Capture opt-in at acceptance, before debounce: enabling the setting
            # later must not authorize requests for already-queued prose.
            identities = [node['id'] for node in reversed(nodes) if node['role'] != 'ooc']
            with self.database.connect() as connection:
                placeholders = ','.join('?' for _ in identities)
                branches = many(connection, f'SELECT * FROM branches WHERE head_id IN ({placeholders})', identities) if identities else []
                eligible = {node['id'] for branch in branches if self.automatic_enabled(connection, branch)
                            for node in path_nodes(connection, branch['head_id'])}
                restored = {row['id'] for row in many(connection, f'SELECT id FROM archive_origins WHERE id IN ({placeholders})', identities)} if identities else set()
            selected = [identity for identity in identities if identity in eligible and identity not in restored]
            if selected:
                self.loop.call_soon_threadsafe(self.schedule_automatic, selected)

    @staticmethod
    def automatic_enabled(connection, branch):
        story, policy = story_policy(connection, branch)
        return not story['archived'] and policy.mode == 'long' and policy.relationship_recall and policy.relationship_automatic

    def schedule_automatic(self, node_ids):
        for identity in node_ids:
            self.pending_nodes[identity] = None
            self.pending_nodes.move_to_end(identity)
        while len(self.pending_nodes) > 64:
            self.pending_nodes.popitem(last=False)
        if self.dispatcher is None or self.dispatcher.done():
            self.dispatcher = asyncio.create_task(self.automatic())
            self.automatic_tasks.add(self.dispatcher)
            self.dispatcher.add_done_callback(self.automatic_tasks.discard)

    async def automatic(self):
        while self.pending_nodes:
            await asyncio.sleep(1)
            node_ids = set(self.pending_nodes)
            self.pending_nodes.clear()
            try:
                ids = await asyncio.to_thread(self.prepare_automatic, node_ids)
                for identity in ids:
                    self.start_job(identity)
            except Exception:
                continue  # Unsupported/inactive background work never falls through to foreground inference.

    def prepare_automatic(self, node_ids):
        ids = []
        with self.database.connect(write=True) as connection:
            placeholders = ','.join('?' for _ in node_ids)
            if not placeholders:
                return ids
            branches = many(connection, f'SELECT b.id FROM branches b WHERE b.head_id IN ({placeholders})', tuple(node_ids))
            for branch in branches:
                try:
                    plan = plan_requests(connection, branch['id'], node_ids=node_ids)
                    if plan['snapshots'] and self.provider.background_capability(plan['snapshots'][0]['profile'])['verified']:
                        ids.extend(insert_jobs(connection, plan, 'automatic')['job_ids'])
                except DomainError:
                    continue
        return ids

    def start_job(self, identity):
        if identity not in self.tasks:
            task = asyncio.create_task(self.run(identity))
            self.tasks[identity] = task
            task.add_done_callback(lambda _: self.tasks.pop(identity, None))

    def validate(self, identity):
        with self.database.connect() as connection:
            job = one(connection, 'SELECT * FROM relationship_jobs WHERE id=?', (identity,))
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (job['branch_id'],))
            story, policy = story_policy(connection, branch)
            require_agent(connection, 'writer', story)
            require(not story['archived'] and policy.mode == 'long' and policy.relationship_recall,
                    'Relationship preparation was disabled.', 409)
            require(job['mode'] != 'automatic' or policy.relationship_automatic,
                    'Automatic relationship preparation was disabled.', 409)
            sources, _ = source_catalog(connection, branch)
            require(job_sources(job, sources) is not None, 'Relationship source scope changed. Prepare current sources explicitly.', 409)
            return job

    async def watch(self):
        while True:
            for identity, task in list(self.tasks.items()):
                try:
                    await asyncio.to_thread(self.validate, identity)
                except DomainError:
                    if not task.cancelling():
                        task.cancel()
            await asyncio.sleep(0.25)

    def claim(self, identity):
        # A replay of an old operation must not rewrite a completed receipt when
        # its current story policy or source scope has since changed.
        with self.database.connect() as connection:
            if one(connection, 'SELECT status FROM relationship_jobs WHERE id=?', (identity,))['status'] != 'queued':
                return None
        job = self.validate(identity)
        with self.database.connect(write=True) as connection:
            changed = connection.execute("UPDATE relationship_jobs SET status='running',attempt=attempt+1 WHERE id=? AND status='queued'", (identity,))
        return job if changed.rowcount else None

    async def run(self, identity):
        state = {'status': 'running', 'output': '', 'result': None, 'usage': {'calls': 0}, 'error': ''}
        started = time.monotonic()
        try:
            job = await asyncio.to_thread(self.claim, identity)
            if job is None:
                state = None
                return
            snapshot = decode(job['snapshot'])
            work = Work(35 if job['mode'] == 'automatic' else 15, 'relationship preparation', job['mode'] == 'automatic',
                        lambda: self.validate(identity))
            with work_scope(work):
                await self.consume(identity, snapshot, state, automatic=job['mode'] == 'automatic')
            self.validate(identity)
            state.update(status='done', result=parse_annotations(state['output'], snapshot))
        except asyncio.CancelledError:
            state.update(status='cancelled', error='Stopped. Partial output is preserved; retry is explicit.')
        except BackgroundInterrupted:
            state.update(status='cancelled', error='Yielded to foreground work. Retry this annotation explicitly.')
        except DomainError as error:
            state.update(status='error', error=error.message)
        except Exception:
            state.update(status='error', error='Relationship preparation failed or returned invalid annotations. Exact prose and ordinary recall are unchanged.')
        finally:
            if state is not None:
                state['usage']['seconds'] = time.monotonic() - started
                self.save(identity, state, final=True)

    async def consume(self, identity, snapshot, state, automatic=False):
        # Native background prediction already caps output at 1,200. Keep the verified
        # saved configuration identity intact; the outer deadline still caps time.
        profile = snapshot['profile'] if automatic else extraction_profile(snapshot['profile'])
        state['usage']['calls'] = 1
        self.save(identity, state)
        async with asyncio.timeout(min(60, profile['config']['timeout_seconds'])):
            async with aclosing(self.provider.generate(profile, snapshot['prompt_text'], snapshot['content'])) as events:
                async for event in events:
                    state['output'] += event.text
                    state['usage'].update(event.usage)
                    if event.model:
                        state['usage']['actual_model'] = event.model
                    require(len(state['output']) <= MAX_OUTPUT, 'Relationship preparation exceeded its output limit.', 502)
                    self.save(identity, state)

    def save(self, identity, state, final=False):
        with self.database.connect(write=True) as connection:
            connection.execute('UPDATE relationship_jobs SET status=?,output=?,result=?,usage=?,error=?,updated_at=? WHERE id=?',
                               (state['status'], state['output'][:MAX_OUTPUT], encode(state['result']), encode(state['usage']), state['error'], now(), identity))
            if final:
                preserve_attempt(connection, identity, 'relationship')

    def cancel(self, identity):
        with self.database.connect(write=True) as connection:
            one(connection, 'SELECT id FROM relationship_jobs WHERE id=?', (identity,))
            connection.execute("UPDATE relationship_jobs SET status='cancelled',error='Stopped before dispatch.' WHERE id=? AND status='queued'", (identity,))
        if identity in self.tasks:
            self.tasks[identity].cancel()
        return {'stopped': True}

    def retry(self, identity):
        require(identity not in self.tasks, 'Wait for this relationship request to stop.', 409)
        job = self.validate(identity)
        require(job['status'] in {'error', 'cancelled', 'interrupted'}, 'Retry only an unfinished relationship request.', 409)
        with self.database.connect(write=True) as connection:
            preserve_attempt(connection, identity, 'relationship')
            connection.execute("UPDATE relationship_jobs SET status='queued',output='',result='null',usage='{}',error='' WHERE id=?", (identity,))
        self.start_job(identity)
        return {'retried': True}

    async def shutdown(self):
        if self.changed in self.database.node_listeners:
            self.database.node_listeners.remove(self.changed)
        tasks = [*self.tasks.values(), *self.automatic_tasks, *([self.watcher] if self.watcher else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
