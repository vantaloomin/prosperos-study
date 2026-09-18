import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from server.errors import DomainError
from server.providers.config import ProfileConfig
from server.providers.http import HttpProvider
from server.providers.lmstudio import NativeStream
from tests.test_providers import events


def config(**extra):
    return ProfileConfig(provider='local', model='chosen', local_protocol='lmstudio', **extra).model_dump()


def end(text='A story.', **stats):
    return {'type': 'chat.end', 'result': {'model_instance_id': 'actual',
        'output': [{'type': 'message', 'content': text}], 'stats': stats}}


async def collect(provider, settings, received):
    async for event in provider.generate(settings, 'fixture-key', 'Exact prompt', 'Exact input'):
        received.append(event)


@pytest.mark.parametrize('reasoning', [None, 'off', 'on', 'low', 'medium', 'high'])
def test_native_request_and_visible_only_stream(reasoning):
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == '/api/v1/chat'
        expected = {'model': 'chosen', 'system_prompt': 'Exact prompt', 'input': 'Exact input',
                    'stream': True, 'store': False, 'integrations': [], 'max_output_tokens': 1200}
        if reasoning is not None:
            expected['reasoning'] = reasoning
        assert body == expected
        return httpx.Response(200, text=events(
            {'type': 'reasoning.delta', 'content': 'PRIVATE reasoning'},
            {'type': 'message.delta', 'content': 'A '},
            {'type': 'message.delta', 'content': 'story.'},
            end(input_tokens=45, total_output_tokens=90, reasoning_output_tokens=80)))
    received = []
    asyncio.run(collect(HttpProvider(httpx.MockTransport(handler)), config(local_reasoning=reasoning), received))
    assert ''.join(row.text for row in received) == 'A story.'
    assert 'PRIVATE' not in repr(received)
    assert received[-1].model == 'actual' and received[-1].done
    assert received[-1].usage['reasoning_tokens'] == 80
    assert 'finish_reason' not in received[-1].usage


@pytest.mark.parametrize('base,expected', [
    ('http://localhost:1234', 'http://localhost:1234/api/v1'),
    ('http://localhost:1234/v1/', 'http://localhost:1234/api/v1'),
    ('http://localhost:1234/proxy/api/v1/', 'http://localhost:1234/proxy/api/v1'),
    ('http://localhost:1234/proxy/v1', 'http://localhost:1234/proxy/api/v1')])
def test_native_url_normalization_is_idempotent(base, expected):
    settings = config(base_url=base)
    assert settings['base_url'] == expected
    assert ProfileConfig.model_validate(settings).model_dump() == settings


@pytest.mark.parametrize('values', [
    {'provider': 'openai', 'local_protocol': 'lmstudio'},
    {'provider': 'local', 'local_reasoning': 'off'},
    {'provider': 'local', 'local_protocol': 'lmstudio', 'temperature': 1.1},
    {'provider': 'local', 'local_protocol': 'lmstudio', 'base_url': 'https://example.com'},
    {'provider': 'local', 'local_protocol': 'lmstudio', 'local_reasoning': 'unsupported'},
])
def test_invalid_native_settings_are_rejected(values):
    with pytest.raises(ValidationError):
        ProfileConfig(model='chosen', **values)


def test_legacy_local_settings_stay_compatible():
    settings = ProfileConfig(provider='local', model='chosen').model_dump()
    assert settings['base_url'].endswith('/v1') and '/api/' not in settings['base_url']
    assert settings['local_protocol'] == 'openai' and settings['local_reasoning'] is None


@pytest.mark.parametrize('tail,match', [
    ([], 'connection ended'),
    (['[DONE]'], 'connection ended'),
    ([end('Different')], 'differs'),
    ([end('Partial', total_output_tokens=1200)], 'without reporting a stop reason'),
    ([{'type': 'tool_call.start'}], 'requested a tool'),
    ([{'type': 'error', 'error': {'message': 'fixture-key'}}], 'interrupted'),
    ([{'type': 'error', 'error': {'param': 'reasoning', 'message': 'fixture-key'}}], 'reasoning setting'),
    ([end('Partial', input_tokens=True)], 'invalid token'),
    ([{'type': []}], 'invalid event type'),
])
def test_failed_native_stream_preserves_only_received_text(tail, match):
    provider = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200,
        text=events({'type': 'message.delta', 'content': 'Partial'}, *tail))))
    received = []
    with pytest.raises(DomainError, match=match) as error:
        asyncio.run(collect(provider, config(), received))
    assert 'fixture-key' not in str(error.value)
    assert ''.join(row.text for row in received) == 'Partial'


def test_final_aggregate_suffix_is_delivered_once_and_trailing_data_rejected():
    parser = NativeStream(1200)
    first = parser({'type': 'message.delta', 'content': 'A '})
    last = parser(end())
    assert first.text + last.text == 'A story.'
    with pytest.raises(DomainError, match='after completing'):
        parser({'type': 'message.delta', 'content': 'extra'})


def test_final_reasoning_only_is_not_a_success_even_without_usage():
    message = {'type': 'chat.end', 'result': {'output': [{'type': 'reasoning', 'content': 'PRIVATE'}]}}
    received = []
    provider = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(200, text=events(message))))
    with pytest.raises(DomainError, match='reasoning but no response text'):
        asyncio.run(collect(provider, config(), received))
    assert 'PRIVATE' not in repr(received)


def test_native_discovery_uses_loaded_limits_and_reported_options_only():
    def handler(request):
        assert request.method == 'GET' and request.url.path == '/api/v1/models'
        return httpx.Response(200, json={'models': [
            {'type': 'embedding', 'key': 'embed'},
            {'type': 'llm', 'key': 'chosen', 'max_context_length': 131072,
             'loaded_instances': [{'config': {'context_length': 32768}}, {'config': {'context_length': 16384}}],
             'capabilities': {'reasoning': {'allowed_options': ['on', 'off', 'unknown'], 'default': 'on'}}},
            {'type': 'llm', 'key': 'unreported'}]})
    result = asyncio.run(HttpProvider(httpx.MockTransport(handler)).check(config(), None))
    assert result['models'] == ['chosen', 'unreported'] and not result['generated']
    chosen, unknown = result['model_details']
    assert chosen['context_tokens'] == 16384 and chosen['max_output_tokens'] is None
    assert chosen['reasoning_options'] == ['off', 'on'] and chosen['reasoning_default'] == 'on'
    assert unknown['context_tokens'] is None and unknown['reasoning_options'] == []


def test_native_and_compatible_calls_to_one_local_endpoint_share_capacity():
    from server.providers.events import ProviderEvent
    from server.providers.service import ProviderService
    from tests.test_profiles import MemoryVault

    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()
        active = peak = entered = 0

        class DelayedTransport:
            async def generate(self, *args):
                nonlocal active, peak, entered
                active += 1
                entered += 1
                peak = max(peak, active)
                started.set()
                try:
                    await release.wait()
                    yield ProviderEvent(text='A story.', done=True)
                finally:
                    active -= 1

        service = ProviderService(MemoryVault(), http=DelayedTransport())
        async def call(settings):
            return [row async for row in service.generate({'config': settings}, 'prompt', 'content')]

        first = asyncio.create_task(call(ProfileConfig(provider='local', model='chosen').model_dump()))
        await asyncio.wait_for(started.wait(), 1)
        second = asyncio.create_task(call(config()))
        try:
            await asyncio.sleep(.01)
            assert entered == 1
        finally:
            release.set()
            await asyncio.gather(first, second)
        assert peak == 1 and entered == 2

    asyncio.run(exercise())
