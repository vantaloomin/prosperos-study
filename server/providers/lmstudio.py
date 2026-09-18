"""Explicit LM Studio native API support; no implicit protocol switching."""
from dataclasses import dataclass
from math import isfinite

from server.errors import DomainError, require
from server.providers.events import ProviderEvent

REASONING_OPTIONS = ('off', 'on', 'low', 'medium', 'high')


def native_local(config):
    return config['provider'] == 'local' and config.get('local_protocol') == 'lmstudio'


def native_base(url):
    base = url.rstrip('/')
    if base.endswith('/api/v1'):
        return base
    return (base[:-3] if base.endswith('/v1') else base) + '/api/v1'


def native_request(config, prompt, content):
    body = {'model': config['model'], 'system_prompt': prompt, 'input': content,
            'stream': True, 'store': False, 'integrations': [],
            'max_output_tokens': config['max_output_tokens']}
    if config.get('temperature') is not None:
        body['temperature'] = config['temperature']
    if config.get('local_reasoning') is not None:
        body['reasoning'] = config['local_reasoning']
    return '/chat', body


def native_failure(data):
    error = data.get('error') or {}
    if isinstance(error, dict) and error.get('param') == 'reasoning':
        return DomainError('LM Studio rejected the reasoning setting for this model. Test the connection and choose a reported option.', 502)
    return DomainError('LM Studio interrupted this response. Check its server logs. Any partial text is preserved.', 502)


def native_usage(stats, limit):
    require(isinstance(stats, dict), 'LM Studio returned invalid usage metadata.', 502)
    names = {'input_tokens': 'input_tokens', 'total_output_tokens': 'output_tokens',
             'reasoning_output_tokens': 'reasoning_tokens', 'tokens_per_second': 'tokens_per_second',
             'time_to_first_token_seconds': 'time_to_first_token_seconds'}
    usage = {}
    for source, target in names.items():
        if source not in stats:
            continue
        value = stats[source]
        require(type(value) in {int, float} and isfinite(value) and value >= 0,
                'LM Studio returned invalid token or timing metadata.', 502)
        usage[target] = value
    if usage.get('reasoning_tokens', 0) > 0:
        usage['reasoning_received'] = True
    if usage.get('output_tokens', 0) >= limit:
        usage['output_limit_uncertain'] = True
    return usage


def final_text(result):
    outputs = result.get('output')
    require(isinstance(outputs, list), 'LM Studio returned an invalid final response.', 502)
    text = []
    for item in outputs:
        require(isinstance(item, dict) and item.get('type') in {'message', 'reasoning'},
                'This response contains an unsupported output or tool call. This step does not use tools.', 502)
        if item['type'] == 'message':
            require(isinstance(item.get('content'), str), 'LM Studio returned invalid message text.', 502)
            text.append(item['content'])
    return ''.join(text)


@dataclass
class NativeStream:
    limit: int
    output: str = ''
    ended: bool = False

    def __call__(self, data):
        require(not self.ended, 'LM Studio sent data after completing its response.', 502)
        kind = data.get('type', '')
        require(isinstance(kind, str), 'LM Studio returned an invalid event type.', 502)
        if kind == 'error':
            raise native_failure(data)
        if kind.startswith('tool_call.'):
            raise DomainError('The model requested a tool. This step does not use tools; partial text is preserved.', 502)
        if kind.startswith('reasoning.'):
            return ProviderEvent(usage={'reasoning_received': True})
        if kind == 'message.delta':
            text = data.get('content')
            require(isinstance(text, str), 'LM Studio returned invalid message text.', 502)
            self.output += text
            return ProviderEvent(text=text)
        if kind == 'chat.end':
            return self.finish(data)
        return ProviderEvent()

    def finish(self, data):
        result = data.get('result')
        require(isinstance(result, dict), 'LM Studio returned an invalid final response.', 502)
        text = final_text(result)
        require(text.startswith(self.output), 'LM Studio final text differs from its streamed response. Partial text is preserved.', 502)
        remaining = text[len(self.output):]
        self.output = text
        self.ended = True
        usage = native_usage(result.get('stats', {}), self.limit)
        if any(item['type'] == 'reasoning' for item in result['output']):
            usage['reasoning_received'] = True
        return ProviderEvent(text=remaining, done=True, model=result.get('model_instance_id'), usage=usage)
