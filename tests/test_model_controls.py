import pytest
from pydantic import ValidationError

from server.providers.capabilities import input_capacity
from server.providers.completion import StreamCompletion
from server.providers.config import ProfileConfig
from server.providers.events import anthropic_event, google_event, openai_event
from server.providers.requests import REQUESTS
from server.providers.usage import usage_summary


@pytest.mark.parametrize('provider,options,expected', [
    ('openai', {'reasoning_effort': 'none', 'response_verbosity': 'low', 'top_p': .9}, {'reasoning': {'effort': 'none'}, 'text': {'verbosity': 'low'}, 'top_p': .9}),
    ('anthropic', {'thinking_mode': 'budget', 'thinking_budget_tokens': 1024, 'max_output_tokens': 3000}, {'thinking': {'type': 'enabled', 'budget_tokens': 1024}}),
    ('anthropic', {'thinking_mode': 'adaptive', 'reasoning_effort': 'high'}, {'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'high'}}),
    ('google', {'thinking_mode': 'off', 'top_p': .8, 'top_k': 30}, {'generationConfig': {'maxOutputTokens': 1200, 'topP': .8, 'topK': 30, 'thinkingConfig': {'thinkingBudget': 0}}}),
    ('google', {'reasoning_effort': 'low'}, {'generationConfig': {'maxOutputTokens': 1200, 'thinkingConfig': {'thinkingLevel': 'low'}}}),
    ('openrouter', {'reasoning_effort': 'low', 'min_p': .05}, {'reasoning': {'effort': 'low'}, 'min_p': .05}),
    ('compatible', {'base_url': 'https://example.test/v1', 'compatible_thinking': False, 'output_token_parameter': 'max_completion_tokens', 'seed': 12}, {'chat_template_kwargs': {'enable_thinking': False}, 'max_completion_tokens': 1200, 'seed': 12}),
])
def test_explicit_controls_map_to_provider_protocol(provider, options, expected):
    config = ProfileConfig(provider=provider, model='fixture', **options).model_dump()
    _, body = REQUESTS[provider](config, 'Instructions', 'Story')
    for key, value in expected.items():
        assert body[key] == value


@pytest.mark.parametrize('options', [
    {'provider': 'anthropic', 'thinking_mode': 'budget', 'thinking_budget_tokens': 1024},
    {'provider': 'anthropic', 'thinking_mode': 'adaptive', 'temperature': .6},
    {'provider': 'google', 'thinking_mode': 'off', 'reasoning_effort': 'low'},
    {'provider': 'openai', 'thinking_mode': 'off'},
    {'provider': 'codex', 'top_p': .8},
    {'provider': 'local', 'local_protocol': 'lmstudio', 'top_k': 10},
    {'provider': 'local', 'compatible_thinking': False, 'reasoning_effort': 'high'},
    {'provider': 'openrouter', 'reported_capabilities': {'model_id': 'fixture', 'supported_parameters': []}, 'top_p': .8},
])
def test_unsupported_or_starved_configurations_are_rejected(options):
    with pytest.raises(ValidationError):
        ProfileConfig(model='fixture', **options)


def test_context_safety_and_provider_defaults():
    config = ProfileConfig(provider='openai', model='fixture', context_safety_tokens=500).model_dump()
    assert input_capacity(config) == 14300
    _, body = REQUESTS['openai'](config, '', '')
    assert 'reasoning' not in body and 'temperature' not in body and 'top_p' not in body


@pytest.mark.parametrize('field,limit', [('context_tokens', 8000), ('max_output_tokens', 1000)])
def test_reported_model_capacity_is_a_ceiling(field, limit):
    with pytest.raises(ValidationError, match='provider-reported'):
        ProfileConfig(provider='openai', model='fixture', reported_capabilities={'model_id': 'fixture', field: limit})


def test_usage_accumulates_across_stream_events_without_exposing_thinking():
    import asyncio

    from server.providers.events import ProviderEvent
    from server.providers.service import ProviderService

    class Transport:
        async def generate(self, *_):
            yield ProviderEvent(usage={'input_tokens': 100, 'cache_read_input_tokens': 20})
            yield ProviderEvent(usage={'reasoning_received': True})
            yield ProviderEvent(text='Visible prose.', usage={'output_tokens': 1200, 'finish_reason': 'length'}, done=True)

    service = ProviderService(None)
    service.connection = lambda _: (Transport(), None)

    async def collect():
        return [event async for event in service.generate({'config': ProfileConfig(provider='anthropic', model='fixture').model_dump()}, '', '')]

    events = asyncio.run(collect())
    summary = events[-1].usage['summary']
    assert summary['input_tokens'] == 120 and summary['cached_input_tokens'] == 20
    assert summary['output_tokens'] == 1200 and summary['thinking_tokens'] is None
    assert summary['response_tokens'] is None and summary['cost_usd'] is None
    assert ''.join(event.text for event in events) == 'Visible prose.'


@pytest.mark.parametrize('parser,event', [
    (openai_event, {'type': 'response.incomplete', 'response': {'incomplete_details': {'reason': 'max_output_tokens'}, 'usage': {'input_tokens': 60, 'output_tokens': 1200, 'output_tokens_details': {'reasoning_tokens': 1200}}}}),
    (anthropic_event, {'type': 'message_delta', 'delta': {'stop_reason': 'max_tokens'}, 'usage': {'output_tokens': 1200}}),
    (google_event, {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'Partial prose'}]}}], 'usageMetadata': {'thoughtsTokenCount': 1200}}),
])
def test_limit_events_preserve_usage_before_reporting_failure(parser, event):
    result = parser(event)
    assert result.usage['finish_reason'] == 'length'
    completion = StreamCompletion(completed=True)
    completion.observe(result)
    from server.errors import DomainError
    with pytest.raises(DomainError, match='thinking'):
        completion.validate({'max_output_tokens': 1200})


def test_cost_is_only_reported_when_currency_is_known():
    raw = {'prompt_tokens': 500, 'completion_tokens': 100, 'completion_tokens_details': {'reasoning_tokens': 70}, 'cost': .0123}
    value = usage_summary(raw, 'openrouter')
    assert value['thinking_tokens'] == 70 and value['response_tokens'] == 30
    assert value['cost_credits'] == .0123 and usage_summary(raw, 'compatible')['cost_usd'] is None
    assert usage_summary({}, 'openai')['input_tokens'] is None
    assert usage_summary({'cost': 0}, 'openrouter')['cost_credits'] == 0
    assert usage_summary({'cost': .02, 'currency': 'USD'}, 'compatible')['cost_usd'] == .02
    value = usage_summary({'promptTokenCount': 100, 'candidatesTokenCount': 20, 'thoughtsTokenCount': 300}, 'google')
    assert value['output_tokens'] == 320 and value['response_tokens'] == 20
