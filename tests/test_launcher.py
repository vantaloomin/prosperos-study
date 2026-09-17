import json
from io import BytesIO
from types import SimpleNamespace

import pytest

from scripts import launch_interface as launcher


@pytest.mark.parametrize(('payload', 'expected'), [
    ({'application': 'Roleplay', 'status': 'ok'}, 'ready'),
    ({'application': 'Other service', 'status': 'ok'}, 'foreign'),
    ({'application': 'Roleplay', 'status': 'starting'}, 'foreign'),
    ([], 'foreign'),
])
def test_reuse_requires_the_workspace_health_identity(monkeypatch, payload, expected):
    opener = SimpleNamespace(open=lambda *_args, **_kwargs: BytesIO(json.dumps(payload).encode()))
    monkeypatch.setattr(launcher.urllib.request, 'build_opener', lambda *_: opener)
    assert launcher.probe_workspace('http://127.0.0.1:8765/') == expected


def test_port_is_reserved_before_startup_so_simultaneous_launch_cannot_bind_twice():
    with launcher.reserve_port(0) as first:
        assert launcher.reserve_port(first.getsockname()[1]) is None


def test_second_launch_opens_existing_workspace_without_starting_another_server(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, 'probe_workspace', lambda _: 'ready')
    monkeypatch.setattr(launcher, 'open_interface', opened.append)
    assert launcher.reuse_workspace('http://127.0.0.1:8765/', False) == 0
    assert opened == ['http://127.0.0.1:8765/']
    assert launcher.reuse_workspace('http://127.0.0.1:8765/', True) == 0
    assert len(opened) == 1


def test_foreign_service_is_left_untouched(monkeypatch):
    monkeypatch.setattr(launcher, 'probe_workspace', lambda _: 'foreign')
    monkeypatch.setattr(launcher, 'open_interface', lambda _: pytest.fail('Must not open another service'))
    assert launcher.reuse_workspace('http://127.0.0.1:8765/', False) == 1


def test_reuse_waits_for_an_instance_that_is_still_starting(monkeypatch):
    states = iter(['waiting', 'waiting', 'ready'])
    monkeypatch.setattr(launcher, 'probe_workspace', lambda _: next(states))
    monkeypatch.setattr(launcher.time, 'sleep', lambda _: None)
    assert launcher.reuse_workspace('http://127.0.0.1:8765/', True) == 0
