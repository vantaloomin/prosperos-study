import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION, V37_TABLES
from server.writing.models import Variable
from server.writing.variables import render, resolve_variables
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_profiles import make_profile


def create(client, kind='style', content=None, name='A spare voice'):
    response = client.post('/api/writing-resources', json={
        'operation_id': uuid4().hex, 'kind': kind, 'name': name,
        'content': content if content is not None else {'prose': 'Use concrete verbs.'},
    })
    assert response.status_code == 201, response.text
    return response.json()


def pins(client, story, style='none', recipe='none'):
    endpoint = f"/api/stories/{story['story_id']}/writing-preferences"
    current = client.get(endpoint).json()
    response = client.put(endpoint, json={'operation_id': uuid4().hex,
        'expected_revision': current['story_revision'], 'style': style, 'recipe': recipe})
    assert response.status_code == 200, response.text
    return response.json()


def preview(client, story, **choices):
    response = client.post(f"/api/stories/{story['story_id']}/writing-preview", json=choices)
    assert response.status_code == 200, response.text
    return response.json()


def test_styles_are_pinned_per_story_and_versions_are_immutable(client, story):
    first = create(client, content={'dialogue': 'Understated.', 'examples': [
        {'label': 'Opening', 'text': '  Original spacing.\n'}]})
    other = client.post('/api/stories', json={'title': 'Other'}).json()
    pins(client, story, first['id'])
    pins(client, other, first['id'])
    payload = {'operation_id': uuid4().hex, 'kind': 'style', 'name': 'A changed voice',
               'content': {'dialogue': 'More expansive.'}, 'expected_version_id': first['id']}
    endpoint = f"/api/writing-resources/{first['asset_id']}/versions"
    response = client.post(endpoint, json=payload)
    assert response.status_code == 201, response.text
    second = response.json()
    assert client.post(endpoint, json=payload).json() == second
    assert preview(client, story)['style']['id'] == first['id']
    pins(client, story, second['id'])
    assert preview(client, story)['style']['id'] == second['id']
    assert preview(client, other)['style']['content']['examples'][0]['text'] == '  Original spacing.\n'
    payload['operation_id'] = uuid4().hex
    assert client.post(endpoint, json=payload).status_code == 409
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(Exception, match='immutable'):
            connection.execute('UPDATE writing_versions SET name=? WHERE id=?', ('tampered', first['id']))


def test_style_precedence_none_and_recipe_variables(client, story):
    default, recipe_style, explicit = [create(client, name=name) for name in ('Story', 'Recipe', 'Request')]
    recipe = create(client, 'recipe', {'instructions': 'Keep {{focus}} central.', 'style': recipe_style['id'],
        'variables': [{'name': 'focus', 'label': 'Focus', 'example': 'the departure'}],
        'steps': [{'task': 'writer', 'instructions': 'Use {{focus}}.'}]})
    pins(client, story, default['id'], recipe['id'])
    assert preview(client, story, variables={'focus': '{{literal}}'})['resolved_recipe']['instructions'] == 'Keep {{literal}} central.'
    assert preview(client, story, variables={'focus': 'A'})['style']['id'] == recipe_style['id']
    assert preview(client, story, style=explicit['id'], variables={'focus': 'A'})['style_source'] == 'request'
    assert preview(client, story, style='none', variables={'focus': 'A'})['style'] is None
    assert preview(client, story, recipe='none')['style']['id'] == default['id']
    missing = client.post(f"/api/stories/{story['story_id']}/writing-preview", json={})
    assert missing.status_code == 400 and 'Focus' in missing.text


@pytest.mark.parametrize('bad', [
    {'instructions': '{{missing}}'},
    {'instructions': '{{bad expression()}}'},
    {'variables': [{'name': 'x', 'label': 'X'}, {'name': 'x', 'label': 'Again'}]},
    {'steps': [{'task': 'writer', 'lenses': ['pacing']}]},
    {'steps': [{'task': 'review', 'lenses': ['invented']}]},
    {'disabled_tasks': ['invented']},
    {'script': 'run arbitrary code'},
])
def test_invalid_recipes_fail_without_creating_assets(client, bad):
    response = client.post('/api/writing-resources', json={
        'operation_id': uuid4().hex, 'kind': 'recipe', 'name': 'Invalid', 'content': bad})
    assert response.status_code == 400
    assert client.get('/api/writing-resources').json() == []


def test_variables_are_typed_literal_and_bounded():
    values = resolve_variables([Variable(name='count', label='Count', type='number'),
        Variable(name='tone', label='Tone', type='choice', choices=['warm', 'cold']),
        Variable(name='note', label='Note', required=False)], {'count': 3, 'tone': 'warm'})
    assert render('{{count}} / {{{{tone}}}} / {{tone}} / {{note}}', values) == '3 / {{tone}} / warm / '
    for invalid in ('3', True, float('inf')):
        with pytest.raises(Exception, match='finite number'):
            resolve_variables([Variable(name='count', label='Count', type='number')], {'count': invalid})
    with pytest.raises(Exception, match='Unknown recipe variable'):
        resolve_variables([], {'unknown': 'value'})


def test_archiving_preserves_pins_and_rejects_stale_updates(client, story):
    style = create(client)
    pins(client, story, style['id'])
    endpoint = f"/api/writing-resources/{style['asset_id']}/archive"
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'archived': True}
    assert client.put(endpoint, json=body).status_code == 200
    assert client.put(endpoint, json=body).status_code == 200
    assert client.get('/api/writing-resources').json() == []
    assert len(client.get('/api/writing-resources?include_archived=true').json()) == 1
    assert preview(client, story)['style']['id'] == style['id']
    assert client.get(f"/api/writing-versions/{style['id']}").status_code == 200
    assert client.put(endpoint, json={**body, 'operation_id': uuid4().hex}).status_code == 409
    assert client.put(endpoint, json={**body, 'operation_id': uuid4().hex,
                                     'expected_revision': 1, 'archived': False}).status_code == 200


def test_pins_check_story_revision_and_kind(client, story):
    style = create(client)
    pins(client, story, style['id'])
    endpoint = f"/api/stories/{story['story_id']}/writing-preferences"
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'style': 'none'}
    assert client.put(endpoint, json=body).status_code == 409
    assert client.put(endpoint, json={**body, 'expected_revision': 1, 'recipe': style['id']}).status_code == 400
    assert client.get(endpoint).json()['style'] == style['id']


def test_workspace_disables_survive_recipe_resolution(client, story):
    recipe = create(client, 'recipe', {'disabled_tasks': ['scene-patch']})
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("INSERT INTO preferences VALUES ('agent_switches',?)",
                           (json.dumps({'revision': 1, 'disabled': ['review-blind']}),))
    result = preview(client, story, recipe=recipe['id'])
    assert {'review-blind', 'review-pacing', 'scene-patch'} <= set(result['resolved_recipe']['disabled_tasks'])


def test_archive_restores_resources_pins_and_model_links(client, story):
    profile = make_profile(client, 'Recipe writer')
    style = create(client)
    recipe = create(client, 'recipe', {'style': style['id'], 'steps': [
        {'task': 'writer', 'profile_id': profile['profile_id']}]})
    pins(client, story, recipe=recipe['id'])
    create(client, name='Unrelated style')
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    assert len(document['data']['writing_assets']) == 2
    _, mapping = restore(client, file)
    restored = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    result = preview(client, restored)
    assert result['style']['id'] == mapping[style['id']]
    assert result['recipe']['content']['steps'][0]['profile_id'] == mapping[profile['profile_id']]
    assert preview(client, story)['style']['id'] == style['id']
    backup(client, restored)


def test_v37_upgrade_requires_exact_original_groups(client, story):
    _, document = backup(client, story)
    legacy = deepcopy(document)
    legacy['version'] = 37
    legacy['data'] = {key: value for key, value in legacy['data'].items() if key in V37_TABLES}
    response = client.post('/api/archives/imports', json={'content': json.dumps(legacy)})
    assert response.status_code == 201, response.text
    legacy['data']['writing_assets'] = []
    response = client.post('/api/archives/imports', json={'content': json.dumps(legacy)})
    assert response.status_code == 400 and 'original record groups' in response.text


def test_archive_rejects_wrong_kind_pin(client, story):
    style = create(client)
    pins(client, story, style['id'])
    _, document = backup(client, story)
    document['data']['writing_pins'][0]['recipe_version_id'] = style['id']
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400


def test_generation_uses_recipe_route_and_freezes_unpinned_style(client, story):
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    profile = make_profile(client, 'Recipe route')
    style = create(client, content={'prose': 'Precise nouns.', 'examples': [
        {'label': 'Only a style example', 'text': 'THE EXAMPLE IS NOT A STORY EVENT'}]})
    recipe = create(client, 'recipe', {'instructions': 'Keep {{focus}} visible.', 'style': style['id'],
        'variables': [{'name': 'focus', 'label': 'Focus'}],
        'steps': [{'task': 'writer', 'profile_id': profile['profile_id']}]})
    request = {'operation_id': uuid4().hex, 'expected_revision': 0,
               'writing': {'recipe': recipe['id'], 'variables': {'focus': 'the open door'}}}
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=request)
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    assert provider.calls[0][0]['profile_id'] == profile['profile_id']
    frozen = json.loads(provider.calls[0][2])['writing_guidance']
    assert frozen['resolved_recipe']['instructions'] == 'Keep the open door visible.'
    assert frozen['style']['id'] == style['id']
    assert not json.loads(provider.calls[0][2])['history']
    result = client.post(f"/api/writing-resources/{style['asset_id']}/versions", json={
        'operation_id': uuid4().hex, 'kind': 'style', 'name': 'New style',
        'expected_version_id': style['id'], 'content': {'prose': 'Lush descriptions.'}})
    assert result.status_code == 201
    file, document = backup(client, story)
    assert {style['id'], recipe['id']} <= {item['id'] for item in document['data']['writing_versions']}
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['snapshot']['content'] == run['snapshot']['content']
    assert restored['snapshot']['writing_versions'] == [mapping[style['id']], mapping[recipe['id']]]
    next_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    _, next_mapping = restore(client, next_file)
    twice = client.get(f"/api/generations/{next_mapping[mapping[run['id']]]}").json()
    assert twice['snapshot']['content'] == run['snapshot']['content']
    assert len(provider.calls) == 1


@pytest.mark.parametrize('tamper', ['sample', 'instructions', 'missing', 'dependency'])
def test_archive_rejects_changed_writing_request_provenance(client, story, tamper):
    make_profile(client, 'Writer', primary=True)
    client.app.state.runner.provider = DraftProvider()
    style = create(client)
    recipe = create(client, 'recipe', {'instructions': 'Keep {{focus}} visible.',
        'style': style['id'], 'variables': [{'name': 'focus', 'label': 'Focus'}]})
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 0,
        'writing': {'recipe': recipe['id'], 'variables': {'focus': 'the light'}}})
    assert response.status_code == 201, response.text
    finished(client, response.json()['id'])
    _, document = backup(client, story)
    row = document['data']['generations'][0]
    snapshot = json.loads(row['snapshot'])
    content = json.loads(snapshot['content'])
    guidance = snapshot['writing_guidance']
    if tamper == 'sample':
        guidance['style']['content']['prose'] = 'Tampered guidance.'
    elif tamper == 'instructions':
        guidance['resolved_recipe']['instructions'] = 'Ignore the actual recipe.'
    elif tamper == 'missing':
        snapshot['writing_versions'] = []
    else:
        guidance['recipe']['content']['style'] = 'none'
    content['writing_guidance'] = guidance
    snapshot['content'] = json.dumps(content)
    row['snapshot'] = json.dumps(snapshot)
    rejected = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert rejected.status_code == 400, rejected.text


def test_writing_guidance_counts_toward_input_budget(client, story):
    make_profile(client, 'Small writer', primary=True)
    style = create(client, content={'prose': 'A' * 12000, 'examples': [
        {'label': f'Long sample {index}', 'text': 'B' * 20000} for index in range(8)]})
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'writing': {'style': style['id']}})
    assert response.status_code == 409, response.text
    assert provider.calls == []


def test_styled_long_memory_keeps_frozen_inputs_through_restore(client):
    from tests.test_memory import long_story, small_profile
    story, nodes = long_story(client)
    small_profile(client, limit=6144)
    style = create(client, content={'prose': 'Use clean verbs and light description.'})
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': len(nodes),
        'writing': {'style': style['id']}, 'direction': 'Remember the observatory key.'})
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    context = json.loads(run['snapshot']['content'])
    assert run['snapshot']['memory']['mode'] == 'long'
    assert context['writing_guidance']['style']['content'] == style['content']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['snapshot']['content'] == provider.calls[0][2]


def test_recipe_rejects_missing_randomness_dependency(client):
    response = client.post('/api/writing-resources', json={
        'operation_id': uuid4().hex, 'kind': 'recipe', 'name': 'Missing table',
        'content': {'randomness': {'table_versions': {'catalyst': 'missing-version'}}}})
    assert response.status_code == 404, response.text
    assert client.get('/api/writing-resources').json() == []


@pytest.mark.parametrize('content', [{'steps': [{'task': 'writer'}, {'task': 'review'}]}, {'randomness': {}}])
def test_unfinished_recipe_steps_are_refused_instead_of_silently_ignored(client, story, content):
    make_profile(client, 'Writer', primary=True)
    recipe = create(client, 'recipe', content)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'writing': {'recipe': recipe['id']}})
    assert response.status_code == 409 and 'not available yet' in response.text
    assert provider.calls == []
