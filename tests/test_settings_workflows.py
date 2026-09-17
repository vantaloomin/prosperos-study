from uuid import uuid4

from server.providers.config import ProfileConfig, ProfileCreate
from server.providers.http import HttpProvider
from tests.test_agent_switches import toggle
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_profiles import MemoryVault, make_profile


def test_key_only_connection_can_be_completed_and_archived(client, monkeypatch):
    client.app.state.vault = MemoryVault()
    saved = client.post('/api/profiles', json={'api_key': 'private-draft-key', 'make_primary': True,
                                              'config': {'provider': 'openrouter'}})
    assert saved.status_code == 201
    profile = saved.json()
    assert profile['name'] and profile['has_saved_key'] and not profile['ready']
    assert client.get('/api/profiles').json()['primary_profile_id'] is None
    assert client.put('/api/profiles/primary', json={'profile_id': profile['profile_id']}).status_code == 409
    file, document = backup(client)
    assert 'private-draft-key' not in str(document)
    _, mapping = restore(client, file)
    restored = next(row for row in client.get('/api/profiles').json()['profiles'] if row['profile_id'] == mapping[profile['profile_id']])
    assert not restored['ready'] and not restored['has_saved_key']
    seen = []
    async def check(_self, config, key):
        seen.append(key)
        return {'available': True, 'models': ['writer']}
    monkeypatch.setattr(HttpProvider, 'check', check)
    assert client.post('/api/profiles/discover', json={'config': profile['config'], 'profile_id': profile['profile_id'], 'expected_version_id': profile['id']}).status_code == 200
    assert seen == ['private-draft-key']
    complete = client.put('/api/profiles/' + profile['profile_id'], json={'expected_version_id': profile['id'], 'make_primary': True,
                           'config': {**profile['config'], 'model': 'writer'}}).json()
    assert complete['ready'] and complete['has_saved_key']
    assert client.get('/api/profiles').json()['primary_profile_id'] == profile['profile_id']


def test_unbound_compatible_key_binds_once_then_does_not_cross_endpoints(client):
    client.app.state.vault = MemoryVault()
    saved = client.post('/api/profiles', json={'api_key': 'unbound-secret', 'config': {'provider': 'compatible'}})
    assert saved.status_code == 201
    profile = saved.json()
    assert not profile['ready']
    assert client.post('/api/profiles/' + profile['profile_id'] + '/check').status_code == 409
    body = {'expected_version_id': profile['id'], 'config': {'provider': 'compatible', 'model': 'writer', 'base_url': 'https://first.test/v1'}}
    complete = client.put('/api/profiles/' + profile['profile_id'], json=body).json()
    assert complete['ready'] and complete['has_saved_key']
    body['expected_version_id'] = complete['id']
    body['config']['base_url'] = 'https://second.test/v1'
    changed = client.put('/api/profiles/' + profile['profile_id'], json=body).json()
    assert not changed['has_saved_key']


def test_incomplete_profile_never_starts_generation(client, story):
    client.app.state.vault = MemoryVault()
    profile = client.post('/api/profiles', json={'api_key': 'secret', 'config': {'provider': 'openrouter'}}).json()
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'profile_ids': [profile['profile_id']]})
    assert response.status_code == 409 and 'Finish this connection' in response.text
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []


def test_section_switch_is_atomic_scoped_and_keeps_versions(client):
    toggle(client, 'writer', False)
    before = client.get('/api/prompts').json()
    group = [row for row in before if row['group'] == 'Interactive writing']
    assert len({row['enabled'] for row in group}) == 2
    body = {'group': 'Interactive writing', 'enabled': True, 'expected_revision': group[0]['activation_revision']}
    assert client.put('/api/prompt-sections/activation', json=body).status_code == 200
    after = client.get('/api/prompts').json()
    assert all(row['enabled'] for row in after if row['group'] == body['group'])
    assert [row['id'] for row in before] == [row['id'] for row in after]
    body['enabled'] = False
    assert client.put('/api/prompt-sections/activation', json=body).status_code == 409
    assert client.get('/api/prompts').json() == after
    body['expected_revision'] += 1
    assert client.put('/api/prompt-sections/activation', json=body).status_code == 200
    disabled = client.get('/api/prompts').json()
    assert all(not row['enabled'] for row in disabled if row['group'] == body['group'])
    assert all(row['enabled'] for row in disabled if row['group'] != body['group'])
    body['group'] = 'unknown'
    assert client.put('/api/prompt-sections/activation', json=body).status_code == 404


def test_followup_uses_saved_contribution_once_and_keeps_draft_separate(client, story):
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    make_profile(client, 'Automatic writer', primary=True)
    receipt = client.post(f"/api/branches/{story['branch_id']}/messages", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'text': 'The door opens.', 'role': 'narrator'}).json()
    body = {'operation_id': 'continue-' + receipt['node_id'], 'expected_revision': 1, 'assess_beat': False}
    route = f"/api/branches/{story['branch_id']}/generations"
    first = client.post(route, json=body)
    assert first.status_code == 201
    assert client.post(route, json=body).json() == first.json()
    finished(client, first.json()['id'])
    assert len(provider.calls) == 1 and 'The door opens.' in provider.calls[0][2]
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert [row['text'] for row in branch['messages']] == ['The door opens.']


def test_complete_typed_profiles_remain_compatible_with_connection_drafts():
    body = ProfileCreate(name='Existing caller', config=ProfileConfig(provider='local', model='writer'))
    assert body.config.model == 'writer'
