from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import encode
from server.providers.lmstudio_background import VERIFICATION_SECONDS, fingerprint
from server.providers.scheduling import resource_for
from tests.test_profiles import make_profile
from tests.test_relationship_recall import prepare, wait_jobs
from tests.test_writer_recall import change_memory, setup_story


def status(client, story, **params):
    response = client.get(f"/api/branches/{story['branch_id']}/memory-readiness", params=params)
    assert response.status_code == 200, response.text
    result = response.json()
    return result, {row['key']: row for row in result['items']}


def settings(client, story, **changes):
    current = client.get(f"/api/stories/{story['story_id']}").json()
    body = {key: current[key] for key in ('title', 'premise', 'archived', 'settings')}
    body['settings'].update(changes)
    response = client.put(f"/api/stories/{story['story_id']}", json={**body, 'expected_revision': current['revision']})
    assert response.status_code == 200, response.text


def test_missing_writer_and_full_history_are_reported_without_creating_work(client, story):
    with client.app.state.database.connect() as connection:
        before = list(connection.iterdump())
    result, rows = status(client, story)
    assert result['writer'] is None and 'Primary Writer' in result['writer_reason']
    assert rows['local']['state'] == 'full history'
    assert rows['semantic']['state'] == rows['relationships']['state'] == rows['background']['state'] == 'off'
    with client.app.state.database.connect() as connection:
        assert list(connection.iterdump()) == before


def test_inactive_dependencies_are_not_presented_as_working(client, story):
    make_profile(client, 'Writer', primary=True)
    change_memory(client, story, mode='long', semantic_recall=True, relationship_recall=True, relationship_automatic=True)
    _, rows = status(client, story)
    assert rows['prewriting']['state'] == 'off'
    assert rows['semantic']['state'] == rows['relationships']['state'] == 'inactive'
    assert rows['background']['state'] == 'paused'
    change_memory(client, story, mode='full', writer_recall=True)
    _, rows = status(client, story)
    assert rows['prewriting']['state'] == rows['background']['state'] == 'inactive'


def test_production_routing_and_background_writer_remain_distinct(client, story):
    primary = make_profile(client, 'Workspace writer', primary=True)
    default = make_profile(client, 'Story writer')
    step = make_profile(client, 'Step writer')
    override = make_profile(client, 'One draft writer')
    assert status(client, story)[0]['writer']['profile_id'] == primary['profile_id']
    settings(client, story, primary_profile_id=default['profile_id'])
    assert status(client, story)[0]['writer']['profile_id'] == default['profile_id']
    settings(client, story, step_profiles={'writer': step['profile_id']})
    change_memory(client, story, mode='long', writer_recall=True, relationship_recall=True, relationship_automatic=True)
    result, rows = status(client, story, profile_id=override['profile_id'])
    assert result['writer']['profile_id'] == override['profile_id']
    assert rows['background']['profile_id'] == step['profile_id']
    assert 'Step writer' in rows['background']['detail']
    settings(client, story, disabled_prompts=['writer'])
    result, rows = status(client, story, profile_id=override['profile_id'])
    assert result['writer'] is None and 'disabled' in result['writer_reason']
    assert rows['prewriting']['state'] == 'unavailable'


@pytest.mark.parametrize(('provider', 'model', 'expected'), [('local', '', 'needs setup'), ('local', 'nomic-test', 'configured'), ('openrouter', 'nomic-test', 'unavailable')])
def test_semantic_configuration_does_not_probe_models(client, story, provider, model, expected):
    profile = client.post('/api/profiles', json={'name': 'Writer', 'make_primary': True,
        'config': {'provider': provider, 'model': 'writer', 'embedding_model': model}})
    assert profile.status_code == 201, profile.text
    change_memory(client, story, mode='long', writer_recall=True, semantic_recall=True)
    _, rows = status(client, story)
    assert rows['semantic']['state'] == expected
    assert rows['semantic']['profile_id'] == profile.json()['profile_id']
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []


def test_character_scope_does_not_claim_or_enumerate_full_path_recall(client, story, monkeypatch):
    import server.memory.readiness as readiness
    make_profile(client, 'Writer', primary=True)
    change_memory(client, story, mode='long', writer_recall=True, semantic_recall=True, relationship_recall=True)
    def forbidden(*_args):
        raise AssertionError('Character readiness must not enumerate whole-path relationship evidence')
    monkeypatch.setattr(readiness, 'source_catalog', forbidden)
    _, rows = status(client, story, character_lens=True)
    assert rows['local']['state'] == 'character scope'
    assert rows['prewriting']['state'] == rows['semantic']['state'] == rows['relationships']['state'] == 'inactive'


def test_background_expiry_and_blocked_resource_are_current_without_probes(client, story):
    import time
    profile = client.post('/api/profiles', json={'name': 'Local', 'make_primary': True,
        'config': {'provider': 'local', 'model': 'writer', 'local_protocol': 'lmstudio'}}).json()
    change_memory(client, story, mode='long', relationship_recall=True, relationship_automatic=True)
    provider = client.app.state.relationship_runner.provider
    config = deepcopy(profile['config'])
    proof = {'expires': time.monotonic() + VERIFICATION_SECONDS, 'measurement': {}}
    provider.background.verified[fingerprint(config)] = proof
    assert status(client, story)[1]['background']['state'] == 'eligible'
    resource, _ = resource_for(config)
    provider.scheduler.block(resource, 'Stop was not acknowledged.')
    assert status(client, story)[1]['background']['state'] == 'paused'
    provider.scheduler.blocked.clear()
    proof['expires'] = 0
    assert status(client, story)[1]['background']['state'] == 'paused'


def test_link_count_respects_branch_evidence_and_performs_no_extraction(client):
    from tests.test_relationship_recall import RelationshipProvider
    story, nodes = setup_story(client)
    change_memory(client, story, relationship_recall=True)
    provider = RelationshipProvider()
    client.app.state.relationship_runner.provider = provider
    prepared = prepare(client, story)
    jobs = wait_jobs(client, prepared['job_ids'])
    assert all(job['status'] == 'done' for job in jobs), jobs
    calls = len(provider.calls)
    result, rows = status(client, story)
    assert rows['relationships']['state'] == 'available'
    assert rows['relationships']['detail'].startswith('4 eligible')
    assert len(provider.calls) == calls
    # A real earlier fork only retains annotations whose evidence is present.
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': len(nodes), 'node_id': nodes[0], 'name': 'Before the handoff'})
    assert fork.status_code == 201, fork.text
    assert status(client, fork.json())[1]['relationships']['detail'].startswith('1 eligible')
    assert 'credential_ref' not in encode(result)
