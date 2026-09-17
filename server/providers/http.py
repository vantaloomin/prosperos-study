import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from server.errors import DomainError, require
from server.providers.completion import StreamCompletion
from server.providers.discovery import discover_models
from server.providers.discovery_errors import check_with_deadline
from server.providers.events import (
    ProviderEvent,
    anthropic_event,
    chat_event,
    google_event,
    openai_event,
)
from server.providers.requests import REQUESTS, headers_for, validate_key

PARSERS = {"openai": openai_event, "anthropic": anthropic_event,
           "openrouter": chat_event, "local": chat_event, "compatible": chat_event, "google": google_event}


def check_status(response: httpx.Response):
    descriptions = {401: "Authentication failed. Check the profile's API key.",
                    403: "This account cannot access the selected service or model.",
                    429: "The service reached a rate or usage limit. Retry when it is available."}
    require(response.is_success, descriptions.get(response.status_code,
            f"The service rejected this request (HTTP {response.status_code}). Check its model and settings."), 502)


async def sse_data(response: httpx.Response) -> AsyncIterator[dict]:
    lines = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            lines.append(line[5:].lstrip())
        elif not line and lines:
            yield parse_sse("\n".join(lines))
            lines = []
    if lines:
        yield parse_sse("\n".join(lines))


def parse_sse(value: str) -> dict:
    if value == "[DONE]":
        return {"_done": True}
    try:
        data = json.loads(value)
        require(isinstance(data, dict), "The service returned an invalid stream event.", 502)
        return data
    except json.JSONDecodeError as error:
        raise DomainError("The service returned a malformed stream event.", 502) from error


class HttpProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def generate(self, config: dict, key: str | None, prompt: str, content: str):
        validate_key(config["provider"], key)
        path, body = REQUESTS[config["provider"]](config, prompt, content)
        try:
            async with asyncio.timeout(config["timeout_seconds"]):
                async with httpx.AsyncClient(transport=self.transport, timeout=config["timeout_seconds"],
                                             follow_redirects=False, trust_env=False) as client:
                    async for event in self._request(client, config, key, path, body):
                        yield event
        except (httpx.TimeoutException, TimeoutError) as error:
            raise DomainError("The service timed out. The partial draft is saved; retry is explicit.", 504) from error
        except httpx.RequestError as error:
            raise DomainError("Cannot reach this service. Check the server address and connection.", 502) from error

    async def _request(self, client, config, key, path, body):
        if config["provider"] == "kobold":
            response = await client.post(config["base_url"] + path, headers=headers_for(config, key), json=body)
            check_status(response)
            yield kobold_result(response)
            return
        async with client.stream("POST", config["base_url"] + path,
                                 headers=headers_for(config, key), json=body) as response:
            check_status(response)
            completion = StreamCompletion()
            async for data in sse_data(response):
                event = ProviderEvent(done=True) if data.get("_done") else PARSERS[config["provider"]](data)
                completion.observe(event)
                yield event
            completion.validate(config)

    async def check(self, config: dict, key: str | None) -> dict:
        validate_key(config["provider"], key)
        async with httpx.AsyncClient(transport=self.transport, timeout=15, trust_env=False,
                                     follow_redirects=False) as client:
            return await check_with_deadline(discover_models, client, config, key)



def kobold_result(response: httpx.Response) -> ProviderEvent:
    try:
        text = response.json()["results"][0]["text"]
        require(isinstance(text, str), "Kobold returned an invalid text result.", 502)
        return ProviderEvent(text=text, done=True)
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise DomainError("Kobold did not return a readable generation.", 502) from error
