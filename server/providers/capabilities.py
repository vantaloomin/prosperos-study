"""Explicit adapter contracts; unknown model capabilities are never guessed."""
EFFORTS = ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max')
SAMPLING = {
    'openai': {'temperature', 'top_p'},
    'anthropic': {'temperature', 'top_p', 'top_k'},
    'google': {'temperature', 'top_p', 'top_k'},
    'openrouter': {'temperature', 'top_p', 'top_k', 'min_p', 'frequency_penalty', 'presence_penalty', 'repetition_penalty', 'seed'},
    'compatible': {'temperature', 'top_p', 'top_k', 'min_p', 'frequency_penalty', 'presence_penalty', 'repetition_penalty', 'seed'},
    'local': {'temperature', 'top_p', 'top_k', 'min_p', 'frequency_penalty', 'presence_penalty', 'repetition_penalty', 'seed'},
    'kobold': {'temperature', 'top_p', 'top_k', 'repetition_penalty'},
    'codex': set(),
}


def input_capacity(config):
    return config['context_tokens'] - config['max_output_tokens'] - config.get('context_safety_tokens', 0)


def validate_options(config, archived=False):
    native = config.provider == 'local' and config.local_protocol == 'lmstudio'
    supported = {'temperature'} if native else SAMPLING[config.provider]
    if any(getattr(config, field) is not None for field in set().union(*SAMPLING.values()) - supported):
        raise ValueError('A sampling setting is not supported by this adapter. Clear it or choose another API.')
    validate_thinking(config, native)
    if config.response_verbosity and config.provider != 'openai':
        raise ValueError('Response verbosity is available with the OpenAI Responses adapter.')
    if config.output_token_parameter != 'max_tokens' and (config.provider not in {'compatible', 'local'} or native):
        raise ValueError('The output parameter choice applies to compatible Chat Completions only.')
    if not archived and config.context_safety_tokens + config.max_output_tokens >= config.context_tokens:
        raise ValueError('Context allowance must leave room for input after reserving output and safety tokens.')
    validate_reported(config)


def validate_thinking(config, native):
    provider, mode, budget, effort = config.provider, config.thinking_mode, config.thinking_budget_tokens, config.reasoning_effort
    if effort and (provider == 'kobold' or native):
        raise ValueError('Use the model’s native Thinking control for this adapter.')
    if mode and provider not in {'anthropic', 'openrouter', 'google'}:
        raise ValueError('This adapter does not support this thinking mode.')
    if budget is not None and mode != 'budget':
        raise ValueError('A thinking budget requires budget mode.')
    if mode == 'off' and effort not in {None, 'none'}:
        raise ValueError('Clear reasoning effort before turning thinking off.')
    if mode == 'budget':
        minimum = 1024 if provider == 'anthropic' else (0 if provider == 'openrouter' else -1)
        if budget is None or budget < minimum:
            raise ValueError(f'This thinking budget must be at least {minimum} tokens.')
        if budget >= 0 and budget + config.response_reserve_tokens > config.max_output_tokens:
            raise ValueError('Increase Maximum output tokens or lower the thinking budget to leave the reserved response space.')
    if provider == 'google' and mode == 'adaptive':
        raise ValueError('For Gemini, use an effort level or a dynamic budget of -1.')
    if provider == 'google' and effort and (mode or effort not in {'minimal', 'low', 'medium', 'high'}):
        raise ValueError('Choose one Gemini thinking control: effort level or budget/off.')
    validate_anthropic_thinking(config)
    validate_compatible_thinking(config, native)


def validate_compatible_thinking(config, native):
    if config.compatible_thinking is not None and (config.provider not in {'compatible', 'local'} or native):
        raise ValueError('Chat-template thinking applies to compatible Chat Completions only.')
    if config.compatible_thinking is False and config.reasoning_effort not in {None, 'none'}:
        raise ValueError('Clear reasoning effort before turning chat-template thinking off.')


def validate_anthropic_thinking(config):
    if config.provider != 'anthropic':
        return
    if config.reasoning_effort in {'none', 'minimal'}:
        raise ValueError('Anthropic effort uses low, medium, high, xhigh or max where the model supports it.')
    if config.thinking_mode in {'budget', 'adaptive'}:
        if config.temperature is not None or config.top_k is not None or (config.top_p is not None and config.top_p < .95):
            raise ValueError('With Anthropic thinking, clear temperature and top-k; top-p must be at least 0.95.')


def validate_reported(config):
    info = config.reported_capabilities
    if info is None:
        return
    if info.model_id != config.model:
        raise ValueError('Reported capabilities belong to another model. Test the connection again.')
    if info.context_tokens is not None and config.context_tokens > info.context_tokens:
        raise ValueError('Context allowance exceeds the provider-reported model capacity.')
    if info.max_output_tokens is not None and config.max_output_tokens > info.max_output_tokens:
        raise ValueError('Maximum output tokens exceeds the provider-reported model limit.')
    if info.supported_efforts is not None and config.reasoning_effort and config.reasoning_effort not in info.supported_efforts:
        raise ValueError('The selected effort is not reported as supported by this model.')
    if info.supported_parameters is not None:
        unsupported = [key for key in SAMPLING[config.provider] if getattr(config, key) is not None and key not in info.supported_parameters]
        if unsupported:
            raise ValueError('The model does not report support for: ' + ', '.join(sorted(unsupported)))
        if config.provider == 'openrouter' and (config.reasoning_effort or config.thinking_mode):
            if not {'reasoning', 'reasoning_effort'} & set(info.supported_parameters):
                raise ValueError('The model does not report support for reasoning controls. Leave them at default.')


def request_reasoning(config):
    mode, budget, effort = config.get('thinking_mode'), config.get('thinking_budget_tokens'), config.get('reasoning_effort')
    reasoning = {}
    if effort:
        reasoning['effort'] = effort
    if mode == 'off':
        reasoning['enabled'] = False
    elif mode:
        reasoning['enabled'] = True
    if mode == 'budget':
        reasoning['max_tokens'] = budget
    return reasoning
