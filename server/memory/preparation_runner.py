"""Disposable incremental cache warming; it never selects or accepts story memory."""
import asyncio
import time
from collections import OrderedDict
from threading import Event

from server.memory.chunks import compile_chunks
from server.memory.index import connection_index
from server.memory.retrieval import term_counts

MAX_PENDING = 64
MAX_TEXT = 64_000


def warm_node(database, node, interrupted):
    if node['role'] == 'ooc' or len(node['text']) > MAX_TEXT or interrupted.is_set():
        return 0
    count = 0
    with database.connect() as connection, connection_index(connection):
        chunks = compile_chunks(f"message:{node['id']}", f"{node['role']} passage", node['text'])
        for chunk in chunks:
            if interrupted.is_set():
                break
            term_counts(' '.join((chunk.text, chunk.title, *chunk.aliases)))
            count += 1
    return count


class PreparationRunner:
    def __init__(self, database, scheduler):
        self.database, self.scheduler = database, scheduler
        self.pending = OrderedDict()
        self.task = None
        self.interrupted = Event()
        self.loop = None
        self.stats = {'nodes': 0, 'chunks': 0, 'seconds': 0.0, 'coalesced': 0, 'errors': 0}

    def changed(self, nodes):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.enqueue, nodes)

    def enqueue(self, nodes):
        for node in nodes:
            self.pending[node['id']] = node
            self.pending.move_to_end(node['id'])
        while len(self.pending) > MAX_PENDING:
            self.pending.popitem(last=False)
            self.stats['coalesced'] += 1

    def start(self):
        if self.task:
            return
        self.loop = asyncio.get_running_loop()
        self.database.node_listeners.append(self.changed)
        self.task = asyncio.create_task(self.run())

    async def run(self):
        while True:
            if self.pending and self.scheduler.idle:
                _, node = self.pending.popitem(last=False)
                await self.warm(node)
            await asyncio.sleep(0.1)

    async def warm(self, node):
        self.interrupted.clear()
        started = time.monotonic()
        worker = asyncio.create_task(asyncio.to_thread(warm_node, self.database, node, self.interrupted))
        try:
            while not worker.done():
                if not self.scheduler.idle:
                    self.interrupted.set()
                await asyncio.wait({worker}, timeout=0.02)
            self.stats['chunks'] += worker.result()
            self.stats['nodes'] += 1
        except asyncio.CancelledError:
            self.interrupted.set()
            await asyncio.shield(worker)
            raise
        except Exception:
            # A disposable cache failure must never affect accepted story writes.
            self.stats['errors'] += 1
        finally:
            self.stats['seconds'] += time.monotonic() - started

    async def shutdown(self):
        if self.changed in self.database.node_listeners:
            self.database.node_listeners.remove(self.changed)
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def status(self):
        return {**self.stats, 'pending': len(self.pending), 'max_pending': MAX_PENDING, 'max_text': MAX_TEXT}
