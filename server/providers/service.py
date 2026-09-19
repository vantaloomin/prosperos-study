import time
from contextlib import aclosing

from server.errors import DomainError, require
from server.providers.codex import CodexProvider
from server.providers.config import profile_ready
from server.providers.embeddings import embed
from server.providers.events import ProviderEvent
from server.providers.http import HttpProvider
from server.providers.lmstudio_background import LMStudioBackground
from server.providers.owned_prediction import UnconfirmedStop
from server.providers.restored_connection import credential_reference
from server.providers.scheduling import CURRENT_WORK, RequestScheduler, Work, resource_for
from server.providers.usage import usage_summary
from server.providers.vault import credential_for


class ProviderService:
    def __init__(self, vault, http=None, codex=None, database=None):
        self.vault = vault
        self.database = database
        self.http = http or HttpProvider()
        self.codex = codex or CodexProvider()
        self.scheduler = RequestScheduler()
        self.background = LMStudioBackground()

    def connection(self, profile):
        provider = profile["config"]["provider"]
        key = credential_for(self.vault, provider, credential_reference(self.database, profile))
        transport = self.codex if provider == "codex" else self.http
        return transport, key

    async def generate(self, profile, prompt, content):
        require(profile_ready(profile["config"]), "Finish this model connection in Settings before generating.", 409)
        transport, key = self.connection(profile)
        config = profile["config"]
        work = CURRENT_WORK.get()
        if work.background:
            require(self.background_capability(profile)['verified'],
                    'Background model work needs verified interruption on this connection. '
                    'The original draft and deterministic memory remain available.', 409)
        async with self.scheduler.reserve(config, work) as lease:
            if work.validate:
                work.validate()
            timing = {'queue_seconds': lease.admitted_at - lease.queued_at, 'work': work.kind}
            yield ProviderEvent(usage={'scheduling': timing.copy()})
            stream = (self.background.generate_interruptible(config, key, prompt, content, lease.stop)
                      if work.background else transport.generate(config, key, prompt, content))
            first = None
            usage = {}
            try:
                async with aclosing(stream):
                    async for event in stream:
                        if first is None and event.text:
                            first = time.perf_counter()
                            timing['first_text_seconds'] = first - lease.admitted_at
                        usage.update(event.usage)
                        if event.usage:
                            event.usage = {**event.usage, 'summary': usage_summary(usage, config['provider'])}
                        yield event
            except UnconfirmedStop as error:
                self.scheduler.block(lease.resource, error.message)
                raise
            timing['inference_seconds'] = time.perf_counter() - lease.admitted_at
            yield ProviderEvent(usage={'scheduling': timing, 'summary': usage_summary(usage, config['provider'])})

    def background_capability(self, profile):
        _, key = self.connection(profile)
        capability = self.background.capability(profile['config'], key)
        resource, _ = resource_for(profile['config'])
        blocked = self.scheduler.blocked.get(resource)
        return {**capability, 'blocked': bool(blocked), 'verified': capability['verified'] and not blocked,
                'reason': blocked or capability['reason']}

    async def verify_background(self, profile):
        _, key = self.connection(profile)
        async with self.scheduler.reserve(profile['config'], Work(0, 'interruption check')) as lease:
            try:
                return await self.background.verify(profile['config'], key)
            except UnconfirmedStop as error:
                self.scheduler.block(lease.resource, error.message)
                raise
            except DomainError:
                raise
            except Exception as error:
                self.background.revoke(profile['config'])
                raise DomainError('Interruption could not be verified. Check the loaded model and local connection; no verification was saved.', 502) from error

    def reset_background(self, profile):
        resource, _ = resource_for(profile['config'])
        require(not any(item.resource == resource for item in self.scheduler.active), 'Wait for the active request to stop first.', 409)
        self.background.verified.clear()
        self.scheduler.blocked.pop(resource, None)
        self.scheduler.dispatch()

    async def check(self, profile):
        require(profile["config"]["provider"] == "codex" or bool(profile["config"]["base_url"]), "Add the API base URL in Settings before testing this connection.", 409)
        transport, key = self.connection(profile)
        return await transport.check(profile["config"], key)

    async def embed(self, profile, texts):
        # Explicit writing preparation only: this endpoint has no verified background stop protocol.
        require(not CURRENT_WORK.get().background, 'Embeddings cannot run as automatic background inference.', 409)
        _, key = self.connection(profile)
        async with self.scheduler.reserve(profile['config'], CURRENT_WORK.get()):
            return await embed(profile['config'], key, texts, self.http.transport)
