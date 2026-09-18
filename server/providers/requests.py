from urllib.parse import quote

from server.errors import require
from server.providers.capabilities import SAMPLING, request_reasoning
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
    return {key: config[key] for key in SAMPLING[config['provider']] if config.get(key) is not None}


def openai_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    body = {"model": config["model"], "instructions": prompt, "input": content,
            "max_output_tokens": config["max_output_tokens"], "store": False,
            "stream": True, **sampling(config)}
    if config.get("reasoning_effort"):
        body["reasoning"] = {"effort": config["reasoning_effort"]}
    if config.get('response_verbosity'):
        body['text'] = {'verbosity': config['response_verbosity']}
    return "/responses", body


def anthropic_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    body = {"model": config["model"], "system": prompt,
                         "messages": [{"role": "user", "content": content}],
                         "max_tokens": config["max_output_tokens"], "stream": True, **sampling(config)}
    mode = config.get('thinking_mode')
    if mode:
        body['thinking'] = {'type': {'off': 'disabled', 'budget': 'enabled', 'adaptive': 'adaptive'}[mode]}
        if mode == 'budget':
            body['thinking']['budget_tokens'] = config['thinking_budget_tokens']
    if config.get('reasoning_effort'):
        body['output_config'] = {'effort': config['reasoning_effort']}
    return '/messages', body


def chat_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    body = {"model": config["model"], "messages": [{"role": "system", "content": prompt},
            {"role": "user", "content": content}], config.get('output_token_parameter', 'max_tokens'): config["max_output_tokens"],
            "stream": True, **sampling(config)}
    if config["provider"] == "openrouter":
        body["provider"] = {"allow_fallbacks": False, "require_parameters": True}
        if reasoning := request_reasoning(config):
            body['reasoning'] = reasoning
    elif config.get('reasoning_effort'):
        body['reasoning_effort'] = config['reasoning_effort']
    if config.get('compatible_thinking') is not None:
        body['chat_template_kwargs'] = {'enable_thinking': config['compatible_thinking']}
    if config["provider"] in {"openrouter", "local", "compatible"}:
        body["stream_options"] = {"include_usage": True}
    return "/chat/completions", body


def local_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    return native_request(config, prompt, content) if native_local(config) else chat_request(config, prompt, content)


def kobold_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    options = sampling(config)
    if 'repetition_penalty' in options:
        options['rep_pen'] = options.pop('repetition_penalty')
    return "/generate", {"prompt": f"{prompt}\n\n{content}",
                         "max_length": config["max_output_tokens"],
                         "max_context_length": config["context_tokens"], **options}


def google_request(config: dict, prompt: str, content: str) -> tuple[str, dict]:
    model = quote(config['model'].removeprefix('models/'), safe='')
    options = {'maxOutputTokens': config['max_output_tokens'], **sampling(config)}
    for source, target in [('top_p', 'topP'), ('top_k', 'topK')]:
        if source in options:
            options[target] = options.pop(source)
    if config.get('thinking_mode'):
        options['thinkingConfig'] = {'thinkingBudget': 0 if config['thinking_mode'] == 'off' else config['thinking_budget_tokens']}
    elif config.get('reasoning_effort'):
        options['thinkingConfig'] = {'thinkingLevel': config['reasoning_effort']}
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
