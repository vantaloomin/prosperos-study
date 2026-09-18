import pytest

from server.agent_templates import TEMPLATES
from server.database import encode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.prompt_sections import sections_for, system_prompt
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_profiles import make_profile


@pytest.mark.parametrize('experience,mode', [(None, 'active'), ('roleplay', 'active'), ('directed', 'passive'), ('scene', 'passive')])
def test_new_story_materializes_defaults(client, experience, mode):
    settings = {'experience': experience} if experience else {}
    result = client.post('/api/stories', json={'title': 'Template', 'settings': settings})
    assert result.status_code == 201, result.text
    story = client.get('/api/stories/' + result.json()['story_id']).json()
    assert story['settings']['disabled_prompts'] == sorted(TEMPLATES[mode])
    assert story['settings']['agent_template'] == {'mode': mode, 'version': 1, 'customized': False}
    if mode == 'active':
        assert story['settings']['response_length'].startswith('Flexible')


def test_explicit_switches_and_existing_story_are_preserved(client):
    created = client.post('/api/stories', json={'title': 'Explicit', 'settings': {'disabled_prompts': []}}).json()
    story = client.get('/api/stories/' + created['story_id']).json()
    assert story['settings']['disabled_prompts'] == [] and 'agent_template' not in story['settings']
    update = {key: story[key] for key in ['title', 'premise', 'settings']}
    update['expected_revision'] = story['revision']
    update['settings']['experience'] = 'roleplay'
    assert client.put('/api/stories/' + story['id'], json=update).json()['settings']['disabled_prompts'] == []


def test_story_writer_switch_workspace_ceiling_and_stale_updates(client):
    created = client.post('/api/stories', json={'title': 'Switches'}).json()
    endpoint = '/api/stories/' + created['story_id'] + '/agents'
    body = {'expected_revision': 0, 'disabled': ['writer']}
    assert client.put(endpoint, json=body).status_code == 200
    assert client.put(endpoint, json=body).status_code == 409
    make_profile(client, 'Fixture', primary=True)
    request = client.post('/api/branches/' + created['branch_id'] + '/generations', json={
        'operation_id': 'disabled-writer-01', 'expected_revision': 0})
    assert request.status_code == 409 and 'Story setup' in request.text
    assert client.put(endpoint, json={'expected_revision': 1, 'disabled': ['invalid']}).status_code == 400
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("INSERT OR REPLACE INTO preferences VALUES ('agent_switches',?)", (encode({'revision': 1, 'disabled': ['collaborator']}),))
    prompts = client.get('/api/prompts?story_id=' + created['story_id']).json()
    assert next(row for row in prompts if row['key'] == 'collaborator')['enabled_source'] == 'workspace'


@pytest.mark.parametrize('experience', ['roleplay', 'directed', 'scene'])
@pytest.mark.parametrize('agency', ['user', 'shared', None])
def test_composition_is_orthogonal_versioned_and_can_be_disabled(client, experience, agency):
    settings = {'experience': experience, 'player_agency': agency}
    created = client.post('/api/stories', json={'title': 'Sections', 'settings': settings}).json()
    make_profile(client, 'Fixture', primary=True)
    with client.app.state.database.connect() as connection:
        body = GenerateRequest(operation_id='section-preview', expected_revision=0)
        snapshot, _ = generation_snapshot(connection, created['branch_id'], body)
    keys = [item['key'] for item in snapshot['prompt_sections']]
    assert keys == ['section:mode-active' if experience == 'roleplay' else 'section:mode-passive',
                    'section:agency-shared' if agency == 'shared' else 'section:agency-reserved']
    text = system_prompt(snapshot)
    assert text.startswith(snapshot['prompt_sections'][0]['template'])
    assert text.endswith(snapshot['prompt_sections'][1]['template'])
    assert text.index(snapshot['prompt']['template']) > 0
    endpoint = '/api/stories/' + created['story_id'] + '/agents'
    assert client.put(endpoint, json={'expected_revision': 0, 'disabled': [], 'prompt_sections': False}).status_code == 200
    with client.app.state.database.connect() as connection:
        current, _ = generation_snapshot(connection, created['branch_id'], body)
    assert current['prompt_sections'] == []
    assert system_prompt(current) == current['prompt']['template']


def test_persona_is_resolved_and_frozen(client):
    persona = client.post('/api/library', json={'kind': 'persona', 'name': 'Mara', 'content': {}}).json()
    created = client.post('/api/stories', json={'title': 'Named persona', 'attachments': [
        {'asset_id': persona['asset_id'], 'version_id': persona['id']}]}).json()
    make_profile(client, 'Fixture', primary=True)
    with client.app.state.database.connect() as connection:
        snapshot, _ = generation_snapshot(connection, created['branch_id'], GenerateRequest(operation_id='persona-preview', expected_revision=0))
    assert snapshot['prompt_sections'][1]['template'].startswith('Mara BELONGS TO THE USER')
    with client.app.state.database.connect(write=True) as connection:
        row = one(connection, 'SELECT * FROM stories WHERE id=?', (created['story_id'],))
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode({'experience': 'directed', 'player_agency': 'shared'}), row['id']))
    assert snapshot['prompt_sections'][1]['template'].startswith('Mara BELONGS TO THE USER')


def test_archive_keeps_exact_composed_instructions(client):
    created = client.post('/api/stories', json={'title': 'Frozen sections'}).json()
    make_profile(client, 'Fixture', primary=True)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    run = finished(client, generate(client, created)['id'])
    text = system_prompt(run['snapshot'])
    assert provider.calls[0][1] == text
    file, _ = backup(client, created)
    _, mapping = restore(client, file)
    restored = client.get('/api/generations/' + mapping[run['id']]).json()
    assert system_prompt(restored['snapshot']) == text
    assert [item['id'] for item in restored['snapshot']['prompt_sections']] == [mapping[item['id']] for item in run['snapshot']['prompt_sections']]
    assert restored['snapshot']['content'] == run['snapshot']['content']


@pytest.mark.parametrize('role,expected', [
    ('writer', True), ('scene-options', True), ('background-interpretation', True),
    ('scene-draft', True), ('scene-dialogue', True), ('scene-patch', True), ('review-rules', True),
    ('review-pacing', False), ('review-blind', False), ('scribe', False), ('memory-summary', False),
    ('collaborator', False), ('scene-triage', False), ('library-assist', False),
])
def test_sections_respect_role_scope(client, story, role, expected):
    with client.app.state.database.connect() as connection:
        row = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        assert bool(sections_for(connection, role, row)) is expected


def test_original_retry_keeps_sections_after_their_heads_change(client, story):
    from server.providers.events import ProviderEvent

    class FailedProvider(DraftProvider):
        async def generate(self, profile, prompt, content):
            self.calls.append((profile, prompt, content))
            yield ProviderEvent(usage={'finish_reason': 'length'}, done=True)

    make_profile(client, 'Retry fixture', primary=True)
    client.app.state.runner.provider = FailedProvider()
    run = finished(client, generate(client, story)['id'])
    candidate = run['candidates'][0]
    assert candidate['status'] == 'error'
    for section in run['snapshot']['prompt_sections']:
        response = client.put('/api/prompts/' + section['key'], json={
            'expected_version_id': section['id'], 'template': 'Changed after this request.'})
        assert response.status_code == 200, response.text
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    result = client.post('/api/candidates/' + candidate['id'] + '/retry', json={
        'operation_id': 'retry-frozen-sections', 'expected_attempt': 1})
    assert result.status_code == 200, result.text
    assert finished(client, run['id'])['candidates'][0]['status'] == 'done'
    assert provider.calls[0][1] == system_prompt(run['snapshot'])
    assert 'Changed after this request.' not in provider.calls[0][1]
