from urllib.parse import quote

from server.errors import require
from server.providers.lmstudio import native_local, native_request


def headers_for(config: dict, key: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if config["provider"] == "anthropic":
        headers.update({"x-api-key": key or "", "anthropic-version": "2023-06-01"})
    elif config["provider"] == "google":
        headers["x-goog-api-key"] = key or ""
    elif key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def sampling(config: dict) -> dict:
    value = config.get("temperature")
    return {"temperature": value} if value is not None else {}


def openai_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    body = {"model": config["model"], "instructions": prompt, "input": content,
            "max_output_tokens": config["max_output_tokens"], "store": False,
            "stream": True, **sampling(config)}
    if config.get("reasoning_effort"):
        body["reasoning"] = {"effort": config["reasoning_effort"]}
    return "/responses", body


def anthropic_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    return "/messages", {"model": config["model"], "system": prompt,
                         "messages": [{"role": "user", "content": content}],
                         "max_tokens": config["max_output_tokens"], "stream": True, **sampling(config)}


def chat_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    body = {"model": config["model"], "messages": [{"role": "system", "content": prompt},
            {"role": "user", "content": content}], "max_tokens": config["max_output_tokens"],
            "stream": True, **sampling(config)}
    if config["provider"] == "openrouter":
        body["provider"] = {"allow_fallbacks": False, "require_parameters": True}
    if config["provider"] in {"openrouter", "local"}:
        body["stream_options"] = {"include_usage": True}
    return "/chat/completions", body


def local_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    return native_request(config, prompt, content) if native_local(config) else chat_request(config, prompt, content)


def kobold_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    return "/generate", {"prompt": f"{prompt}\n\n{content}",
                         "max_length": config["max_output_tokens"],
                         "max_context_length": config["context_tokens"], **sampling(config)}


def google_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    model = quote(config['model'].removeprefix('models/'), safe='')
    options = {'maxOutputTokens': config['max_output_tokens'], **sampling(config)}
    return f'/models/{model}:streamGenerateContent?alt=sse', {
        'systemInstruction': {'parts': [{'text': prompt}]},
        'contents': [{'role': 'user', 'parts': [{'text': content}]}],
        'generationConfig': options,
    }


REQUESTS = {"openai": openai_request, "anthropic": anthropic_request,
            "openrouter": chat_request, "local": local_request, "kobold": kobold_request,
            "compatible": chat_request, "google": google_request}


def validate_key(provider: str, key: str | None):
    if provider in {"openai", "anthropic", "openrouter", "google"}:
        require(bool(key), "This profile needs an API key. Add it in Models or set the provider environment variable.", 409)
