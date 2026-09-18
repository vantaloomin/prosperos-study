"""Native discovery reports loaded limits and supported reasoning options."""
from server.errors import require
from server.providers.lmstudio import REASONING_OPTIONS


def positive(value):
    return value if type(value) is int and value > 0 else None


def loaded_context(item):
    instances = item.get('loaded_instances')
    if not isinstance(instances, list):
        return None
    values = [positive(row['config'].get('context_length')) for row in instances
              if isinstance(row, dict) and isinstance(row.get('config'), dict)]
    return min((value for value in values if value is not None), default=None)


def reasoning_details(item):
    capabilities = item.get('capabilities')
    reasoning = capabilities.get('reasoning') if isinstance(capabilities, dict) else None
    if not isinstance(reasoning, dict) or not isinstance(reasoning.get('allowed_options'), list):
        return {'reasoning_options': [], 'reasoning_default': None}
    options = [value for value in REASONING_OPTIONS if value in reasoning['allowed_options']]
    default = reasoning.get('default')
    return {'reasoning_options': options, 'reasoning_default': default if default in options else None}


def native_model(item):
    if not isinstance(item, dict) or item.get('type') != 'llm':
        return None
    key = item.get('key')
    if not isinstance(key, str) or not key.strip():
        return None
    context = loaded_context(item) or positive(item.get('max_context_length'))
    return {'id': key, 'name': str(item.get('display_name') or key), 'context_tokens': context,
            'max_output_tokens': None, 'limit_source': 'provider' if context else 'unreported',
            **reasoning_details(item)}


def native_models(data):
    require(isinstance(data.get('models'), list), 'LM Studio returned an invalid native model list.', 502)
    details = [detail for row in data['models'] if (detail := native_model(row))]
    return {'available': True, 'models': [row['id'] for row in details], 'model_details': details,
            'generated': False, 'note': 'Connected to LM Studio. Loaded context limits and supported thinking options are reported when available.'}
