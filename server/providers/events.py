from dataclasses import dataclass, field

from server.errors import DomainError


@dataclass
class ProviderEvent:
    text: str = ""
    usage: dict = field(default_factory=dict)
    done: bool = False
    model: str | None = None


def openai_event(data: dict) -> ProviderEvent:
    kind = data.get("type")
    if kind == "response.output_text.delta":
        return ProviderEvent(text=data["delta"])
    if kind in {'response.completed', 'response.incomplete'}:
        response = data["response"]
        usage = dict(response.get('usage') or {})
        if kind == 'response.incomplete':
            reason = (response.get('incomplete_details') or {}).get('reason')
            usage['finish_reason'] = 'length' if reason == 'max_output_tokens' else 'unrecognized'
        if (usage.get('output_tokens_details') or {}).get('reasoning_tokens', 0):
            usage['reasoning_received'] = True
        return ProviderEvent(usage=usage, done=True, model=response.get("model"))
    if kind in {"error", "response.failed"}:
        raise DomainError("The provider did not complete this response. The partial draft is preserved.", 502)
    return ProviderEvent()


def anthropic_event(data: dict) -> ProviderEvent:
    kind = data.get("type")
    if kind == "content_block_delta":
        delta = data.get('delta', {})
        return ProviderEvent(text=delta.get('text', ''), usage={'reasoning_received': True} if delta.get('type') == 'thinking_delta' else {})
    if kind == "message_start":
        message = data["message"]
        return ProviderEvent(usage=message.get("usage", {}), model=message.get("model"))
    if kind == "message_delta":
        usage = dict(data.get('usage') or {})
        reason = data.get('delta', {}).get('stop_reason')
        if reason:
            usage['finish_reason'] = {'end_turn': 'stop', 'stop_sequence': 'stop', 'max_tokens': 'length', 'tool_use': 'tool_calls'}.get(reason, 'unrecognized')
        return ProviderEvent(usage=usage)
    if kind == "error":
        raise DomainError("The provider interrupted this response. The partial draft is preserved.", 502)
    return ProviderEvent(done=kind == "message_stop")


def google_event(data: dict) -> ProviderEvent:
    if data.get('error') or data.get('promptFeedback', {}).get('blockReason'):
        raise DomainError('Google could not return this response. Review the request or choose another model.', 502)
    candidates = data.get('candidates', [])
    candidate = candidates[0] if candidates else {}
    finish = candidate.get('finishReason')
    parts = candidate.get('content', {}).get('parts', [])
    text = ''.join(part.get('text', '') for part in parts if not part.get('thought'))
    usage = dict(data.get('usageMetadata') or {})
    if finish:
        usage['finish_reason'] = {'STOP': 'stop', 'MAX_TOKENS': 'length', 'SAFETY': 'content_filter'}.get(finish, 'unrecognized')
    if any(part.get('thought') for part in parts) or usage.get('thoughtsTokenCount', 0):
        usage['reasoning_received'] = True
    return ProviderEvent(text=text, done=bool(finish), usage=usage, model=data.get('modelVersion'))


def chat_event(data: dict) -> ProviderEvent:
    if data.get("error"):
        raise DomainError("The provider reported a generation error. Check the selected model.", 502)
    choices = data.get("choices", [])
    choice = choices[0] if choices else {}
    delta = choice.get("delta") or {}
    return ProviderEvent(text=delta.get("content") or "", usage=chat_usage(data, choice, delta),
                         model=data.get("model"))


def chat_usage(data: dict, choice: dict, delta: dict) -> dict:
    usage = dict(data.get("usage") or {})
    reason = choice.get("finish_reason")
    if reason:
        allowed = {"stop", "length", "content_filter", "tool_calls", "function_call"}
        usage["finish_reason"] = reason if reason in allowed else "unrecognized"
    tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    reported_reasoning = isinstance(tokens, (int, float)) and tokens > 0
    if reported_reasoning or any(delta.get(key) for key in ("reasoning_content", "reasoning", "reasoning_details")):
        usage["reasoning_received"] = True
    return usage
