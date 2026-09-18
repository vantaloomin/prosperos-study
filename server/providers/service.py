import asyncio

from server.errors import require
from server.providers.codex import CodexProvider
from server.providers.config import profile_ready
from server.providers.http import HttpProvider
from server.providers.lmstudio import native_base
from server.providers.restored_connection import credential_reference
from server.providers.vault import credential_for


class ProviderService:
    def __init__(self, vault, http=None, codex=None, database=None):
        self.vault = vault
        self.database = database
        self.http = http or HttpProvider()
        self.codex = codex or CodexProvider()
        self.limits = {}

    def connection(self, profile):
        provider = profile["config"]["provider"]
        key = credential_for(self.vault, provider, credential_reference(self.database, profile))
        transport = self.codex if provider == "codex" else self.http
        return transport, key

    async def generate(self, profile, prompt, content):
        require(profile_ready(profile["config"]), "Finish this model connection in Settings before generating.", 409)
        transport, key = self.connection(profile)
        config = profile["config"]
        address = native_base(config["base_url"]) if config["provider"] == "local" else config["base_url"]
        endpoint = (config["provider"], address)
        concurrency = 1 if config["provider"] in {"local", "kobold", "codex"} else 2
        limit = self.limits.setdefault(endpoint, asyncio.Semaphore(concurrency))
        async with limit:
            async for event in transport.generate(config, key, prompt, content):
                yield event

    async def check(self, profile):
        require(profile["config"]["provider"] == "codex" or bool(profile["config"]["base_url"]), "Add the API base URL in Settings before testing this connection.", 409)
        transport, key = self.connection(profile)
        return await transport.check(profile["config"], key)
