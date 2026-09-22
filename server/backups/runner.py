import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from server.backups.storage import recover

logger = logging.getLogger(__name__)


class BackupRunner:
    def __init__(self, backups):
        self.backups = backups
        self.task = None
        self.stopping = asyncio.Event()
        self.poll_seconds = 30

    def start(self):
        recover(self.backups.database)
        self.stopping.clear()
        self.task = asyncio.create_task(self.loop())

    async def loop(self):
        while not self.stopping.is_set():
            try:
                await run_in_threadpool(self.backups.run)
            except Exception:
                logger.exception('Backup scheduler could not check for due work; it will retry.')
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def shutdown(self):
        self.stopping.set()
        if self.task:
            # Let an atomic write finish; cancelling its thread would leave recovery ambiguous.
            await self.task
            self.task = None
