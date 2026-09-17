import asyncio
import json

import httpx
import pytest

from server.errors import DomainError
from server.providers.config import ProfileConfig
from server.providers.events import chat_event
from server.providers.http import HttpProvider
from tests.test_generations import finished, generate
from tests.test_profiles import make_profile
from tests.test_providers import collect, events


def chat_stream(text="", reason="length", reasoning_key="reasoning_content"):
    return events(
        {"choices": [{"delta": {reasoning_key: "private-reasoning-marker"}}]},
        {"choices": [{"delta": {"content": text}, "finish_reason": reason}]},
        {"choices": [], "usage": {"completion_tokens": 1200,
                                  "completion_tokens_details": {"reasoning_tokens": 1200}}},
        "[DONE]",
    )


@pytest.mark.parametrize("provider", ["local", "compatible", "openrouter"])
@pytest.mark.parametrize("text", ["", "A preserved partial sentence"])
def test_token_limit_is_not_success_and_preserves_usage(provider, text):
    body = chat_stream(text)
    config = ProfileConfig(provider=provider, model="test", base_url="https://example.test/v1"
                           if provider == "compatible" else "").model_dump()
    http = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    received = []

    async def run():
        async for event in http.generate(config, "fixture-key", "Instructions", "Input"):
            received.append(event)

    with pytest.raises(DomainError) as failure:
        asyncio.run(run())
    assert "token limit" in str(failure.value)
    assert "1,200" in str(failure.value)
    assert ("partial text" if text else "Only reasoning") in str(failure.value)
    assert "".join(event.text for event in received) == text
    assert "private-reasoning-marker" not in repr(received)
    assert any(event.usage.get("finish_reason") == "length" for event in received)
    assert any(event.usage.get("completion_tokens") == 1200 for event in received)


@pytest.mark.parametrize("key", ["reasoning_content", "reasoning", "reasoning_details"])
def test_reasoning_can_precede_a_successful_visible_answer(key):
    body = chat_stream("A complete answer.", "stop", key)
    http = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    result = asyncio.run(collect(http, ProfileConfig(provider="local", model="test").model_dump()))
    assert "".join(event.text for event in result) == "A complete answer."
    assert any(event.done for event in result)
    assert "private-reasoning-marker" not in repr(result)


@pytest.mark.parametrize("reason,expected", [
    ("stop", "reasoning but no response text"),
    ("content_filter", "content filter"),
    ("tool_calls", "requested a tool"),
    ("function_call", "requested a function"),
    ("private-provider-value", "unsupported completion reason"),
])
def test_non_text_completion_has_specific_safe_error(reason, expected):
    http = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=chat_stream(reason=reason))))
    with pytest.raises(DomainError) as failure:
        asyncio.run(collect(http, ProfileConfig(provider="local", model="test").model_dump()))
    assert expected in str(failure.value)
    assert "private-provider-value" not in str(failure.value)


@pytest.mark.parametrize("text,expected", [("", "No response text"), ("Partial", "partial text")])
def test_token_limit_without_reasoning_does_not_claim_thinking(text, expected):
    body = events({"choices": [{"delta": {"content": text}, "finish_reason": "length"}]}, "[DONE]")
    http = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    with pytest.raises(DomainError) as failure:
        asyncio.run(collect(http, ProfileConfig(provider="local", model="test").model_dump()))
    assert expected in str(failure.value)
    assert "Only reasoning" not in str(failure.value)


def test_usage_only_reasoning_is_detected_without_exposing_reasoning():
    event = chat_event({"choices": [], "usage": {"completion_tokens_details": {"reasoning_tokens": 42}}})
    assert event.usage["reasoning_received"]
    assert not event.text
    assert chat_event({"choices": [{"delta": None}], "usage": None}).usage == {}


@pytest.mark.parametrize("text", ["", "Saved partial prose."])
def test_failed_reasoning_draft_preserves_attempt_and_frozen_retry(client, story, text):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["stream_options"] == {"include_usage": True}
        return httpx.Response(200, text=chat_stream(text))

    client.app.state.runner.provider.http = HttpProvider(httpx.MockTransport(handler))
    profile = make_profile(client, "Reasoning writer", primary=True)
    run = generate(client, story)
    detail = finished(client, run["id"])
    candidate = detail["candidates"][0]
    assert candidate["status"] == "error"
    assert candidate["output"] == text
    assert "1,200" in candidate["error"]
    assert candidate["usage"]["completion_tokens"] == 1200
    assert candidate["usage"]["finish_reason"] == "length"
    assert "private-reasoning-marker" not in json.dumps(detail)
    assert client.post(f"/api/candidates/{candidate['id']}/accept", json={"operation_id": "cannot-accept"}).status_code == 409
    assert client.get(f"/api/branches/{story['branch_id']}").json()["messages"] == []
    updated = client.put(f"/api/profiles/{profile['profile_id']}", json={
        "expected_version_id": profile["id"], "name": "Reasoning writer",
        "config": {**profile["config"], "max_output_tokens": 8192},
    })
    assert updated.status_code == 200
    assert client.post(f"/api/candidates/{candidate['id']}/retry").status_code == 200
    retry = finished(client, run["id"])
    assert retry["candidates"][0]["attempt"] == 2
    assert [request["max_tokens"] for request in requests] == [1200, 1200]
    attempts = client.get(f"/api/candidates/{candidate['id']}/attempts").json()
    assert len(attempts) == 2
    assert all(attempt["output"] == text for attempt in attempts)
    assert all(attempt["usage"]["finish_reason"] == "length" for attempt in attempts)
