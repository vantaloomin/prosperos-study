"""Normalize reported counts only; missing cost is unknown, never zero."""
from math import isfinite


def number(value):
    return value if type(value) in {int, float} and isfinite(value) and value >= 0 else None


def nested(data, key, field):
    value = data.get(key)
    return number(value.get(field)) if isinstance(value, dict) else None


def first(*values):
    return next((value for value in values if value is not None), None)


def usage_summary(usage, provider):
    input_tokens = first(number(usage.get('input_tokens')), number(usage.get('prompt_tokens')), number(usage.get('promptTokenCount')))
    output = first(number(usage.get('output_tokens')), number(usage.get('completion_tokens')), number(usage.get('candidatesTokenCount')))
    thinking = first(number(usage.get('reasoning_tokens')), nested(usage, 'output_tokens_details', 'reasoning_tokens'),
                     nested(usage, 'output_tokens_details', 'thinking_tokens'), nested(usage, 'completion_tokens_details', 'reasoning_tokens'),
                     number(usage.get('thoughtsTokenCount')))
    cached = first(nested(usage, 'input_tokens_details', 'cached_tokens'), nested(usage, 'prompt_tokens_details', 'cached_tokens'),
                   number(usage.get('cache_read_input_tokens')), number(usage.get('cachedContentTokenCount')))
    if provider == 'anthropic' and input_tokens is not None:
        input_tokens += (number(usage.get('cache_creation_input_tokens')) or 0) + (cached or 0)
    if provider == 'google' and output is not None:
        output += thinking or 0
    # OpenRouter names its unit credits. Never infer a conversion or invent an unreported charge.
    cost = number(usage.get('cost')) if usage.get('currency') == 'USD' else None
    credits = number(usage.get('cost')) if provider == 'openrouter' else None
    result = {'input_tokens': input_tokens, 'output_tokens': output, 'thinking_tokens': thinking,
              'cached_input_tokens': cached, 'cost_usd': cost, 'cost_credits': credits,
              'cost_source': 'provider' if cost is not None or credits is not None else None}
    result['response_tokens'] = max(0, output - thinking) if output is not None and thinking is not None else None
    return result
