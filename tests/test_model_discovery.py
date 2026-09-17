import asyncio
import json

import httpx
import pytest

from server.errors import DomainError
from server.providers.config import DiscoveryConfig, ProfileConfig
from server.providers.http import HttpProvider
from tests.test_profiles import MemoryVault
from tests.test_providers import collect, events


@pytest.mark.parametrize('provider,payload,expected', [
    ('openai', {'data': [{'id': 'model-a'}]}, (None, None)),
    ('anthropic', {'data': [{'id': 'model-a', 'max_input_tokens': 200000, 'max_tokens': 32000}]}, (200000, 32000)),
    ('openrouter', {'data': [{'id': 'model-a', 'context_length': 65536, 'top_provider': {'max_completion_tokens': 8192}}]}, (65536, 8192)),
    ('local', {'data': [{'id': 'model-a', 'max_model_len': 32768}]}, (32768, None)),
    ('compatible', {'data': [{'id': 'model-a', 'context_length': 64000}]}, (64000, None)),
    ('kobold', {'result': 'model-a'}, (None, None)),
])
def test_discovery_reports_only_service_limits_without_generating(provider, payload, expected):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload)
    extra = {'base_url': 'https://example.test/v1'} if provider == 'compatible' else {}
    config = DiscoveryConfig(provider=provider, **extra).model_dump()
    result = asyncio.run(HttpProvider(httpx.MockTransport(handler)).check(config, 'fixture-key'))
    assert result['models'] == ['model-a'] and result['generated'] is False
    detail = result['model_details'][0]
    assert (detail['context_tokens'], detail['max_output_tokens']) == expected
    assert calls[0].method == 'GET' and len(calls) == 1
    assert 'fixture-key' not in str(calls[0].url)


def test_google_pages_filter_non_writing_models_and_use_key_header():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers['x-goog-api-key'] == 'fixture-key'
        assert 'fixture-key' not in str(request.url)
        if len(calls) == 1:
            return httpx.Response(200, json={'models': [{'name': 'models/embed', 'supportedGenerationMethods': ['embedContent']}], 'nextPageToken': 'next'})
        assert request.url.params['pageToken'] == 'next'
        return httpx.Response(200, json={'models': [{'name': 'models/writer', 'displayName': 'Writer', 'inputTokenLimit': 1000000,
            'outputTokenLimit': 64000, 'supportedGenerationMethods': ['generateContent']}]})
    result = asyncio.run(HttpProvider(httpx.MockTransport(handler)).check(DiscoveryConfig(provider='google').model_dump(), 'fixture-key'))
    assert result['models'] == ['writer']
    assert result['model_details'][0]['context_tokens'] == 1000000


def test_google_native_stream_uses_system_context_and_omits_thoughts():
    calls = []
    body = events({'candidates': [{'content': {'parts': [{'text': 'Private reasoning', 'thought': True}, {'text': 'A beginning.'}]}}]},
        {'candidates': [{'finishReason': 'STOP'}], 'usageMetadata': {'promptTokenCount': 17}, 'modelVersion': 'actual'})
    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=body)
    config = ProfileConfig(provider='google', model='models/writer').model_dump()
    result = asyncio.run(collect(HttpProvider(httpx.MockTransport(handler)), config))
    assert ''.join(event.text for event in result) == 'A beginning.'
    assert result[-1].done and result[-1].usage['promptTokenCount'] == 17
    request = calls[0]
    assert request.url.path == '/v1beta/models/writer:streamGenerateContent'
    assert request.url.params['alt'] == 'sse'
    assert request.headers['x-goog-api-key'] == 'fixture-key'
    payload = json.loads(request.content)
    assert payload['systemInstruction']['parts'][0]['text'] == 'Editable instructions'
    assert payload['contents'][0]['parts'][0]['text'] == 'Frozen context'
    assert 'tools' not in payload


@pytest.mark.parametrize('body', [events({'candidates': [{'finishReason': 'MAX_TOKENS'}]}),
    events({'promptFeedback': {'blockReason': 'SAFETY'}}), events({'candidates': [{'content': {'parts': [{'text': 'Partial'}]}}]})])
def test_google_incomplete_and_blocked_responses_are_not_success(body):
    config = ProfileConfig(provider='google', model='writer').model_dump()
    with pytest.raises(DomainError):
        asyncio.run(collect(HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=body))), config))


def test_compatible_generation_uses_custom_chat_endpoint():
    def handler(request):
        assert str(request.url) == 'https://example.test/api/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer fixture-key'
        return httpx.Response(200, text=events({'choices': [{'delta': {'content': 'Compatible prose'}}]}, '[DONE]'))
    config = ProfileConfig(provider='compatible', model='writer', base_url='https://example.test/api/v1/').model_dump()
    assert ''.join(item.text for item in asyncio.run(collect(HttpProvider(httpx.MockTransport(handler)), config))) == 'Compatible prose'


def test_unsaved_probe_is_ephemeral_and_saved_key_never_crosses_endpoints(client, monkeypatch):
    vault = client.app.state.vault = MemoryVault()
    seen = []
    async def check(_self, config, key):
        seen.append((config, key))
        return {'available': True, 'models': ['writer'], 'model_details': [], 'generated': False}
    monkeypatch.setattr(HttpProvider, 'check', check)
    monkeypatch.delenv('ROLEPLAY_COMPATIBLE_API_KEY', raising=False)
    config = {'provider': 'compatible', 'base_url': 'https://first.test/v1'}
    response = client.post('/api/profiles/discover', json={'config': config, 'api_key': 'transient-secret'})
    assert response.status_code == 200 and 'transient-secret' not in response.text
    assert not client.get('/api/profiles').json()['profiles'] and not vault.values
    saved = client.post('/api/profiles', json={'name': 'A', 'config': {**config, 'model': 'writer'}, 'api_key': 'saved-secret'}).json()
    body = {'config': config, 'profile_id': saved['profile_id'], 'expected_version_id': saved['id']}
    assert client.post('/api/profiles/discover', json=body).status_code == 200
    assert seen[-1][1] == 'saved-secret'
    body['config'] = {**config, 'base_url': 'https://second.test/v1'}
    assert client.post('/api/profiles/discover', json=body).status_code == 200
    assert seen[-1][1] is None
    updated = client.put(f"/api/profiles/{saved['profile_id']}", json={'name': 'B', 'config': {**body['config'], 'model': 'writer'}, 'expected_version_id': saved['id']}).json()
    assert not updated['has_saved_key']
    assert client.post('/api/profiles/discover', json=body).status_code == 409


@pytest.mark.parametrize('url', ['http://public.test/v1', 'https://key@public.test/v1', 'https://public.test/v1?key=secret', 'https://public.test:99999/v1'])
def test_compatible_rejects_unsafe_or_invalid_address(client, url):
    response = client.post('/api/profiles/discover', json={'config': {'provider': 'compatible', 'base_url': url}})
    assert response.status_code == 422
