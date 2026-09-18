from dataclasses import dataclass

from server.errors import DomainError, require
from server.providers.events import ProviderEvent


@dataclass
class StreamCompletion:
    completed: bool = False
    has_text: bool = False
    has_reasoning: bool = False
    finish_reason: str | None = None
    output_limit_uncertain: bool = False

    def observe(self, event: ProviderEvent):
        self.completed = self.completed or event.done
        self.has_text = self.has_text or bool(event.text.strip())
        self.has_reasoning = self.has_reasoning or bool(event.usage.get("reasoning_received"))
        self.finish_reason = event.usage.get("finish_reason") or self.finish_reason
        self.output_limit_uncertain |= bool(event.usage.get("output_limit_uncertain"))

    def validate(self, config: dict):
        require(self.completed, "The connection ended before the service completed its response.", 502)
        if self.output_limit_uncertain:
            raise DomainError(f"LM Studio used the entire {config['max_output_tokens']:,}-token output allowance without reporting a stop reason. "
                              "The response may be incomplete. Any text is preserved; increase the allowance for a new request.", 502)
        if self.finish_reason == "length":
            raise DomainError(self.limit_message(config), 502)
        failures = {
            "content_filter": "The provider stopped this response because of its content filter.",
            "tool_calls": "The model requested a tool instead of completing its response. This step does not run tools.",
            "function_call": "The model requested a function instead of completing its response. This step does not run tools.",
            "unrecognized": "The provider reported an unsupported completion reason. Check its model and settings.",
        }
        if self.finish_reason in failures:
            raise DomainError(failures[self.finish_reason] + " Any partial text is preserved.", 502)
        if self.has_reasoning and not self.has_text:
            raise DomainError("The model returned reasoning but no response text. Check its thinking settings "
                              "or increase Maximum output tokens, then start a new request.", 502)

    def limit_message(self, config: dict) -> str:
        if self.has_text:
            result = "The response is incomplete; its partial text is preserved."
        elif self.has_reasoning:
            result = "Only reasoning was received; no response text was returned."
        else:
            result = "No response text was returned."
        return (f"Generation stopped at a token limit (finish reason: length). {result} "
                f"This request allowed {config['max_output_tokens']:,} output tokens. "
                "Lower the thinking effort or budget, or increase Maximum output tokens in the model profile, then start a new request. "
                "Retrying original inputs keeps the original limit.")
