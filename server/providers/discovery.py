"""Normalize provider-reported model metadata; absent limits are never guessed."""
from server.errors import DomainError, require
from server.providers.discovery_errors import address_hint, fetch_model_page, response_problem
from server.providers.lmstudio import native_local
from server.providers.lmstudio_models import native_models
from server.providers.requests import headers_for


def token_limit(*values):
    return next((value for value in values if type(value) is int and value > 0), None)


def model_detail(provider, item):
    identifier = item.get('id') or item.get('name')
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    if provider == 'google':
        if 'generateContent' not in item.get('supportedGenerationMethods', []):
            return None
        identifier = identifier.removeprefix('models/')
    top = item.get('top_provider') if isinstance(item.get('top_provider'), dict) else {}
    context = token_limit(item.get('context_length'), item.get('max_model_len'), item.get('max_context_length'),
                          item.get('inputTokenLimit'), item.get('max_input_tokens'), top.get('context_length'))
    output = token_limit(item.get('outputTokenLimit'), item.get('max_output_tokens'),
                         item.get('max_tokens'), top.get('max_completion_tokens'))
    label = item.get('displayName') or item.get('display_name') or item.get('name') or identifier
    return {'id': identifier, 'name': str(label), 'context_tokens': context, 'max_output_tokens': output,
            'limit_source': 'provider' if context or output else 'unreported'}


def page_parameters(provider, data):
    if provider == 'google' and data.get('nextPageToken'):
        return {'pageSize': 1000, 'pageToken': data['nextPageToken']}
    if provider == 'anthropic' and data.get('has_more'):
        require(bool(data.get('last_id')), 'The service returned an invalid model page.', 502)
        return {'limit': 1000, 'after_id': data['last_id']}
    return None


def rows_for(provider, data):
    if provider == 'kobold':
        return [{'id': data.get('result')}]
    rows = data.get('models' if provider == 'google' else 'data')
    require(isinstance(rows, list), 'The service returned an invalid model list.', 502)
    return rows


async def discover_models(client, config, key):
    if native_local(config):
        response, data = await fetch_model_page(client, config, headers_for(config, key), {})
        try:
            return native_models(data)
        except DomainError as error:
            raise response_problem(config, response, error.message, address_hint(config)) from error
    provider = config['provider']
    params = {'pageSize': 1000} if provider == 'google' else {}
    models = {}
    for _ in range(20):
        response, data = await fetch_model_page(client, config, headers_for(config, key), params)
        try:
            add_models(models, provider, rows_for(provider, data))
            params = page_parameters(provider, data)
        except DomainError as error:
            raise response_problem(config, response, error.message, address_hint(config)) from error
        if not params:
            break
    return {'available': True, 'models': list(models), 'model_details': list(models.values()), 'generated': False,
            'note': discovery_note(models, params)}


def discovery_note(models, more_pages):
    if more_pages:
        return 'Model list is incomplete; enter an ID manually if needed.'
    if not models:
        return ('Connected, but the service returned no usable models. Load or enable a text-generation model '
                'in the service, then test again, or enter its ID manually.')
    return 'Connection checked without generating text. Unreported limits remain manual.'


def add_models(models, provider, rows):
    for item in rows:
        if isinstance(item, dict):
            detail = model_detail(provider, item)
            if detail:
                models[detail['id']] = detail
