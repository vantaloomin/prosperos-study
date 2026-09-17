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
    if kind == "response.completed":
        response = data["response"]
        return ProviderEvent(usage=response.get("usage", {}), done=True, model=response.get("model"))
    if kind in {"error", "response.failed", "response.incomplete"}:
        raise DomainError("The provider did not complete this response. The partial draft is preserved.", 502)
    return ProviderEvent()


def anthropic_event(data: dict) -> ProviderEvent:
    kind = data.get("type")
    if kind == "content_block_delta":
        return ProviderEvent(text=data.get("delta", {}).get("text", ""))
    if kind == "message_start":
        message = data["message"]
        return ProviderEvent(usage=message.get("usage", {}), model=message.get("model"))
    if kind == "message_delta":
        return ProviderEvent(usage=data.get("usage", {}))
    if kind == "error":
        raise DomainError("The provider interrupted this response. The partial draft is preserved.", 502)
    return ProviderEvent(done=kind == "message_stop")


def google_event(data: dict) -> ProviderEvent:
    if data.get('error') or data.get('promptFeedback', {}).get('blockReason'):
        raise DomainError('Google could not return this response. Review the request or choose another model.', 502)
    candidates = data.get('candidates', [])
    candidate = candidates[0] if candidates else {}
    finish = candidate.get('finishReason')
    if finish and finish != 'STOP':
        raise DomainError('Google stopped before completing this response. The partial draft is preserved.', 502)
    parts = candidate.get('content', {}).get('parts', [])
    text = ''.join(part.get('text', '') for part in parts if not part.get('thought'))
    return ProviderEvent(text=text, done=finish == 'STOP', usage=data.get('usageMetadata', {}), model=data.get('modelVersion'))


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
