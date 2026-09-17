import asyncio

import httpx
import pytest

from server.errors import DomainError
from server.providers.config import DiscoveryConfig
from server.providers.http import HttpProvider

LOCAL = DiscoveryConfig(provider='local', base_url='http://localhost:1234').model_dump()
SECRET = 'fixture-private-api-key'


def check_response(response, config=LOCAL):
    provider = HttpProvider(httpx.MockTransport(lambda _: response))
    return asyncio.run(provider.check(config, SECRET))


@pytest.mark.parametrize('status,expected', [
    (401, 'Authentication failed'), (403, 'Access denied'), (404, 'endpoint not found'),
    (405, 'does not allow GET'), (429, 'rate or usage limit'), (503, 'server logs'),
    (307, 'Redirects are not followed'),
])
def test_discovery_http_errors_include_request_status_and_safe_remedy(status, expected):
    with pytest.raises(DomainError) as caught:
        check_response(httpx.Response(status, json={'error': SECRET}, headers={'location': 'https://other.test/' + SECRET}))
    message = caught.value.message
    assert expected in message
    assert f'GET http://localhost:1234/models returned HTTP {status}' in message
    assert SECRET not in message
    if status in {404, 405}:
        assert 'http://localhost:1234/v1' in message


@pytest.mark.parametrize('payload,expected', [
    ({'error': 'Unexpected endpoint or method. (GET /models) ' + SECRET}, 'error instead of a model list'),
    ({'data': 'invalid ' + SECRET}, 'invalid model list'),
    ([], 'invalid model-list format'),
])
def test_success_status_with_error_payload_is_not_a_successful_connection(payload, expected):
    with pytest.raises(DomainError) as caught:
        check_response(httpx.Response(200, json=payload))
    assert expected in caught.value.message
    assert 'HTTP 200' in caught.value.message
    assert 'http://localhost:1234/v1' in caught.value.message
    assert SECRET not in caught.value.message


def test_html_response_identifies_wrong_endpoint_without_echoing_body():
    with pytest.raises(DomainError) as caught:
        check_response(httpx.Response(200, text='<html>' + SECRET + '</html>'))
    assert 'non-JSON' in caught.value.message
    assert 'GET http://localhost:1234/models returned HTTP 200' in caught.value.message
    assert SECRET not in caught.value.message


@pytest.mark.parametrize('error,expected,status', [
    (httpx.ConnectError('Connection refused ' + SECRET), 'Connection refused', 502),
    (httpx.ConnectError('[Errno 11001] getaddrinfo failed ' + SECRET), 'hostname could not be resolved', 502),
    (httpx.ConnectError('CERTIFICATE_VERIFY_FAILED ' + SECRET), 'TLS connection failed', 502),
    (httpx.ConnectError('All connection attempts failed ' + SECRET), 'connection could not be established', 502),
    (httpx.ConnectTimeout(SECRET), '15-second limit', 504),
    (httpx.ReadTimeout(SECRET), '15-second limit', 504),
    (httpx.RemoteProtocolError(SECRET), 'connection was interrupted', 502),
    (TimeoutError(SECRET), '30-second limit', 504),
])
def test_network_errors_distinguish_causes_and_never_echo_exception_details(error, expected, status):
    def handler(_request):
        raise error
    with pytest.raises(DomainError) as caught:
        asyncio.run(HttpProvider(httpx.MockTransport(handler)).check(LOCAL, SECRET))
    assert expected in caught.value.message
    assert 'GET http://localhost:1234/models' in caught.value.message
    assert caught.value.status == status
    assert SECRET not in caught.value.message


def test_nested_connection_refusal_remains_actionable():
    def handler(_request):
        try:
            raise OSError(10061, 'The target machine actively refused it ' + SECRET)
        except OSError as cause:
            raise httpx.ConnectError('All connection attempts failed') from cause
    with pytest.raises(DomainError, match='Connection refused') as caught:
        asyncio.run(HttpProvider(httpx.MockTransport(handler)).check(LOCAL, SECRET))
    assert SECRET not in caught.value.message


def test_empty_model_list_explains_how_to_proceed():
    result = check_response(httpx.Response(200, json={'data': []}))
    assert result['available'] and not result['models']
    assert 'returned no usable models' in result['note']
    assert 'Load or enable' in result['note']


def test_discovery_route_preserves_actionable_diagnostics(client, monkeypatch):
    original = HttpProvider.check
    async def failing_check(_self, config, key):
        provider = HttpProvider(httpx.MockTransport(lambda _: httpx.Response(405, json={'error': SECRET})))
        return await original(provider, config, key)
    monkeypatch.setattr(HttpProvider, 'check', failing_check)
    response = client.post('/api/profiles/discover', json={'config': LOCAL, 'api_key': SECRET})
    assert response.status_code == 502  # Distinct from a missing app route, which returns 404/405.
    assert 'GET http://localhost:1234/models returned HTTP 405' in response.json()['detail']
    assert 'http://localhost:1234/v1' in response.json()['detail']
    assert SECRET not in response.text
