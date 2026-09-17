import asyncio
import json

import httpx
import pytest

from server.errors import DomainError
from server.providers.codex import codex_arguments, codex_event
from server.providers.config import ProfileConfig
from server.providers.http import HttpProvider


def events(*items):
    return "".join("data: " + (item if isinstance(item, str) else json.dumps(item)) + "\n\n" for item in items)


async def collect(provider, config):
    return [event async for event in provider.generate(config, "fixture-key", "Editable instructions", "Frozen context")]


@pytest.mark.parametrize("provider,body,expected_path", [
    ("openai", events({"type": "response.output_text.delta", "delta": "A beginning."},
                       {"type": "response.completed", "response": {"usage": {"input_tokens": 8}, "model": "actual"}}), "/v1/responses"),
    ("anthropic", events({"type": "message_start", "message": {"usage": {"input_tokens": 8}}},
                          {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "A beginning."}},
                          {"type": "message_stop"}), "/v1/messages"),
    ("openrouter", events({"choices": [{"delta": {"content": "A beginning."}}]}, "[DONE]"), "/api/v1/chat/completions"),
    ("local", events({"choices": [{"delta": {"content": "A beginning."}}]}, "[DONE]"), "/v1/chat/completions"),
])
def test_cloud_and_local_stream_contracts(provider, body, expected_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    config = ProfileConfig(provider=provider, model="chosen-model").model_dump()
    result = asyncio.run(collect(HttpProvider(httpx.MockTransport(handler)), config))
    assert "".join(event.text for event in result) == "A beginning."
    assert any(event.done for event in result)
    assert requests[0].url.path == expected_path
    payload = json.loads(requests[0].content)
    assert payload["model"] == "chosen-model"
    assert "tools" not in payload
    assert "fixture-key" not in requests[0].url.query.decode()


def test_kobold_native_protocol_and_no_fabricated_usage():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/generate"
        assert body["prompt"] == "Editable instructions\n\nFrozen context"
        return httpx.Response(200, json={"results": [{"text": "A local reply."}]})

    config = ProfileConfig(provider="kobold", model="loaded").model_dump()
    result = asyncio.run(collect(HttpProvider(httpx.MockTransport(handler)), config))
    assert result[0].text == "A local reply."
    assert result[0].usage == {}


@pytest.mark.parametrize("body", [events({"choices": [{"delta": {"content": "Partial"}}]}),
                                  "data: this is not JSON\n\n"])
def test_disconnected_or_malformed_stream_is_not_success(body):
    provider = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    config = ProfileConfig(provider="local", model="model").model_dump()
    with pytest.raises(DomainError):
        asyncio.run(collect(provider, config))


def test_http_error_does_not_echo_key_or_provider_payload():
    provider = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(401, text="fixture-key")))
    config = ProfileConfig(provider="openai", model="model").model_dump()
    with pytest.raises(DomainError) as failure:
        asyncio.run(collect(provider, config))
    assert "fixture-key" not in str(failure.value)
    assert "Authentication failed" in str(failure.value)


def test_codex_is_noninteractive_read_only_and_disables_external_tools():
    config = ProfileConfig(provider="codex", model="chosen-model").model_dump()
    args = codex_arguments("codex.exe", config, "isolated-folder")
    assert "--ignore-user-config" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert args[args.index("--cd") + 1] == "isolated-folder"
    assert 'web_search="disabled"' in args
    assert "mcp_servers={}" in args
    assert args[args.index("shell_tool") - 1] == "--disable"
    assert args[-1] == "-"
    assert codex_event({"type": "item.completed", "item": {"type": "agent_message", "text": "Draft"}}).text == "Draft"
    assert codex_event({"type": "turn.completed", "usage": {"output_tokens": 3}}).done


def test_codex_returns_final_message_without_agent_progress_text():
    from server.providers.codex import codex_output

    class Process:
        async def wait(self):
            return 0

    async def run():
        process = Process()
        process.stdout = asyncio.StreamReader()
        for text in ("I will write the scene.", "The actual story draft."):
            process.stdout.feed_data((json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}) + "\n").encode())
        process.stdout.feed_data(b'{"type":"turn.completed","usage":{"output_tokens":5}}\n')
        process.stdout.feed_eof()
        return [event async for event in codex_output(process)]

    result = asyncio.run(run())
    assert len(result) == 1
    assert result[0].text == "The actual story draft."
