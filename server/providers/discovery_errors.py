"""Actionable discovery diagnostics without echoing credentials or response bodies."""
import asyncio
from urllib.parse import urlsplit

import httpx

from server.errors import DomainError


def model_endpoint(config):
    path = '/model' if config['provider'] == 'kobold' else '/models'
    return config['base_url'].rstrip('/') + path


def address_hint(config):
    base = config['base_url'].rstrip('/')
    if config['provider'] == 'local':
        if not urlsplit(base).path:
            return f'For LM Studio, set Server address to {base}/v1 and test again (include /v1).'
        return ('Check the OpenAI-compatible API base URL in LM Studio, normally '
                'http://127.0.0.1:1234/v1. Do not include /models or /chat/completions.')
    return 'Check the API base URL and API version; do not include the model-list endpoint.'


def response_problem(config, response, explanation, action):
    return DomainError(f'{explanation} GET {model_endpoint(config)} returned HTTP '
                       f'{response.status_code}. {action}', 502)


def check_discovery_status(config, response):
    if response.is_success:
        return
    hints = {
        401: ('Authentication failed.', 'Check the API key, including any authentication enabled in your local server.'),
        403: ('Access denied.', 'Check the API key permissions and whether this account can list models.'),
        404: ('Model-list endpoint not found.', address_hint(config)),
        405: ('The server does not allow GET on this model-list endpoint.', address_hint(config)),
        429: ('The service reached a rate or usage limit.', 'Wait before retrying, or check your account quota.'),
    }
    if response.is_redirect:
        explanation, action = ('The model-list endpoint redirected the request.',
                               'Use the final API base URL directly. Redirects are not followed with your API key.')
    else:
        explanation, action = hints.get(response.status_code, (
            'The service could not return its model list.',
            'Check the service status and server logs, then retry.'))
    raise response_problem(config, response, explanation, action)


def read_model_response(config, response):
    check_discovery_status(config, response)
    try:
        data = response.json()
    except ValueError as error:
        raise response_problem(config, response, 'The server responded with non-JSON data.',
                               address_hint(config)) from error
    if not isinstance(data, dict):
        raise response_problem(config, response, 'The server returned an invalid model-list format.',
                               address_hint(config))
    if 'error' in data:
        raise response_problem(config, response, 'The server returned an error instead of a model list.',
                               address_hint(config) + ' Check its server logs for the provider error.')
    return data


def connection_reason(error):
    # Inspect causes only to classify them. Never copy exception text into a user-facing error.
    causes = []
    for _ in range(8):
        if error is None:
            break
        causes.append(str(error).lower())
        error = error.__cause__ or error.__context__
    detail = ' '.join(causes)
    patterns = [
        (('connection refused', 'actively refused', '10061'), 'Connection refused. Nothing accepted a connection at this address and port.'),
        (('getaddrinfo', 'name or service not known', 'nodename nor servname', 'name resolution', '11001'), 'The server hostname could not be resolved. Check its spelling or use its IP address.'),
        (('certificate', 'ssl', 'tls'), 'The TLS connection failed. Check the certificate and whether this server expects http:// or https://.'),
    ]
    for terms, message in patterns:
        if any(term in detail for term in terms):
            return message
    return 'A connection could not be established. Check the hostname, port, and firewall, and confirm the server is running.'


def request_problem(config, error):
    endpoint = f'GET {model_endpoint(config)}'
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        limit = 15 if isinstance(error, httpx.TimeoutException) else 30
        return DomainError(f'The connection test timed out: {endpoint}. No complete model list arrived '
                           f'within the {limit}-second limit. Check the server is responsive, then retry.', 504)
    if isinstance(error, httpx.ConnectError):
        reason = connection_reason(error)
    else:
        reason = 'The connection was interrupted or the server returned invalid HTTP. Check its server logs, then retry.'
    return DomainError(f'{reason} Request: {endpoint}.', 502)


async def fetch_model_page(client, config, headers, params):
    try:
        response = await client.get(model_endpoint(config), headers=headers, params=params)
    except httpx.RequestError as error:
        raise request_problem(config, error) from error
    return response, read_model_response(config, response)


async def check_with_deadline(discover, client, config, key):
    try:
        async with asyncio.timeout(30):
            return await discover(client, config, key)
    except TimeoutError as error:
        raise request_problem(config, error) from error
