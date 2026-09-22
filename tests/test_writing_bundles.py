import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.format import ARCHIVE_VERSION, V38_TABLES
from server.main import create_app
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_profiles import MemoryVault, make_profile
from tests.test_writing_resources import create, pins, preview


def exported(client, version, samples=False):
    response = client.post(f"/api/writing-versions/{version['id']}/export", json={'include_samples': samples})
    assert response.status_code == 200, response.text
    return response.json()


def proposed(client, document, mappings=None):
    response = client.post('/api/writing-bundles/preview', json={'document': document, 'mappings': mappings or {}})
    assert response.status_code == 200, response.text
    return response.json()


def imported(client, document, mappings=None):
    report = proposed(client, document, mappings)
    assert report['can_import'], report['errors']
    body = {'operation_id': uuid4().hex, 'document': document, 'mappings': mappings or {},
            'preview_fingerprint': report['fingerprint']}
    response = client.post('/api/writing-bundles/import', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/writing-bundles/import', json=body).json() == response.json()
    return response.json()


def fixture(client):
    model = make_profile(client, 'Exported writer')
    style = create(client, content={'prose': 'Concrete verbs.', 'examples': [
        {'label': 'Authored example', 'text': '  A sample.\n'}]})
    recipe = create(client, 'recipe', {'style': style['id'], 'instructions': 'Focus on {{focus}}.',
        'variables': [{'name': 'focus', 'label': 'Focus'}],
        'steps': [{'task': 'writer', 'profile_id': model['profile_id']}]})
    return recipe, style, model


def test_export_is_scoped_versioned_and_samples_are_opt_in(client):
    recipe, style, _ = fixture(client)
    create(client, name='Unrelated private preference')
    bundle = exported(client, recipe)
    assert bundle['format'] == 'prospero-writing-bundle' and bundle['version'] == 1
    assert len(bundle['resources']) == 2 and bundle['omitted_samples'] == 1
    assert all(not item['content'].get('examples') for item in bundle['resources'])
    assert 'Unrelated private preference' not in json.dumps(bundle)
    assert style['id'] not in json.dumps(bundle) and recipe['asset_id'] not in json.dumps(bundle)
    assert bundle['references'][0] == {'key': 'model-1', 'kind': 'model', 'name': 'Exported writer'}
    full = exported(client, recipe, True)
    assert full['resources'][1]['content']['examples'] == style['content']['examples']
    assert full['omitted_samples'] == 0


def test_export_omits_credentials_endpoints_and_configuration(client):
    client.app.state.vault = MemoryVault()
    model = client.post('/api/profiles', json={'name': 'Shared model slot', 'api_key': 'private-key-value',
        'config': {'provider': 'openai', 'model': 'private-model-name'}}).json()
    recipe = create(client, 'recipe', {'steps': [{'task': 'writer', 'profile_id': model['profile_id']}]})
    serialized = json.dumps(exported(client, recipe))
    assert all(value not in serialized for value in ('private-key-value', 'private-model-name', 'credential_ref', 'base_url'))


def test_clean_workspace_import_requires_mapping_and_does_not_activate(client, tmp_path):
    recipe, _, _ = fixture(client)
    document = exported(client, recipe, True)
    with TestClient(create_app(tmp_path / 'clean.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as clean:
        story = clean.post('/api/stories', json={'title': 'Clean'}).json()
        report = proposed(clean, document)
        assert not report['can_import'] and report['errors']
        assert clean.get('/api/writing-resources').json() == []
        local = make_profile(clean, 'Local mapping')
        result = imported(clean, document, {'model-1': local['profile_id']})
        root = next(item for item in result['resources'] if item['id'] == result['root_version_id'])
        assert root['content']['steps'][0]['profile_id'] == local['profile_id']
        assert preview(clean, story)['recipe'] is None
        assert clean.get('/api/profiles').json()['primary_profile_id'] is None
        pins(clean, story, recipe=root['id'])
        resolved = preview(clean, story, variables={'focus': '{{literal text}}'})
        assert resolved['resolved_recipe']['instructions'] == 'Focus on {{literal text}}.'
        assert resolved['style']['content']['examples'][0]['text'] == '  A sample.\n'
        assert clean.get(f"/api/branches/{story['branch_id']}/generations").json() == []


def test_preview_change_and_invalid_mapping_cannot_partially_import(client):
    recipe, _, model = fixture(client)
    document = exported(client, recipe)
    mappings = {'model-1': model['profile_id']}
    report = proposed(client, document, mappings)
    changed = client.put(f"/api/profiles/{model['profile_id']}", json={
        'name': 'Changed mapping', 'expected_version_id': model['id'],
        'config': {'provider': 'local', 'model': 'new'}})
    assert changed.status_code == 200
    before = len(client.get('/api/writing-resources').json())
    response = client.post('/api/writing-bundles/import', json={'operation_id': uuid4().hex,
        'document': document, 'mappings': mappings, 'preview_fingerprint': report['fingerprint']})
    assert response.status_code == 409
    assert not proposed(client, document, {'model-1': 'missing-model'})['can_import']
    assert len(client.get('/api/writing-resources').json()) == before


def test_unsupported_fields_survive_versions_export_and_restore_without_executing(client, story):
    original = create(client)
    document = exported(client, original)
    item = document['resources'][0]
    item['content']['future_style'] = {'intent': '  keep this exactly\n', 'enabled': True}
    item['foreign_app'] = ['retained', 7]
    document['future_format_option'] = {'test': True}
    report = proposed(client, document)
    assert report['can_import'] and report['unsupported'][0]['fields'] == [
        'bundle.future_format_option', 'content.future_style', 'resource.foreign_app']
    result = imported(client, document)
    resource = result['resources'][0]
    assert 'future_style' not in resource['content']
    assert resource['unsupported']['content.future_style']['intent'] == '  keep this exactly\n'
    changed = client.post(f"/api/writing-resources/{resource['asset_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': resource['id'], 'kind': 'style',
        'name': resource['name'], 'content': {'prose': 'Changed supported prose.'}}).json()
    pins(client, story, changed['id'])
    assert 'future_style' not in json.dumps(preview(client, story))
    document_again = exported(client, changed)
    assert document_again['resources'][0]['unsupported'] == resource['unsupported']
    file, archive = backup(client, story)
    assert archive['version'] == ARCHIVE_VERSION and len(archive['data']['writing_extras']) == 2
    _, mapping = restore(client, file)
    restored = client.get(f"/api/writing-versions/{mapping[changed['id']]}").json()
    assert restored['unsupported'] == changed['unsupported']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


def test_sensitive_and_sample_extension_metadata_is_excluded_on_export(client):
    style = create(client, content={'examples': [{'label': 'Sample', 'text': 'Private sample.'}]})
    document = exported(client, style, True)
    document['resources'][0]['content']['api_key'] = 'never-share-this-key'
    document['resources'][0]['content']['future_connection'] = {'base_url': 'http://private-host', 'token': 'secret-token'}
    document['resources'][0]['content']['examples'][0]['extra_notes'] = 'Private sample notes.'
    imported_style = imported(client, document)['resources'][0]
    plain = json.dumps(exported(client, imported_style))
    assert all(value not in plain for value in ('never-share-this-key', 'private-host', 'secret-token', 'Private sample'))
    assert 'Private sample notes.' in json.dumps(exported(client, imported_style, True))


def test_valid_large_unicode_resources_can_round_trip_in_one_bundle(client):
    content = {key: '🕯' * 12000 for key in ('prose', 'viewpoint', 'tense', 'dialogue', 'rhythm', 'description', 'avoid')}
    content['examples'] = [{'label': f'Sample {index}', 'text': '🕯' * 20000} for index in range(8)]
    style = create(client, content=content)
    recipe = create(client, 'recipe', {'style': style['id'], 'variables': [
        {'name': f'input_{index}', 'label': f'Input {index}', 'default': '🕯' * 12000}
        for index in range(20)]})
    document = exported(client, recipe, True)
    document['resources'][0]['unsupported'] = {'retained': 'a' * 250000}
    document['resources'][1]['unsupported'] = {'retained': 'b' * 250000}
    assert len(json.dumps(document, ensure_ascii=False).encode('utf-8')) > 2 * 1024 * 1024
    result = imported(client, document)
    restored_style = next(item for item in result['resources'] if item['kind'] == 'style')
    assert restored_style['content'] == style['content']


def test_external_style_mapping_and_explicit_model_default(client):
    recipe, _, _ = fixture(client)
    document = exported(client, recipe)
    document['resources'] = document['resources'][:1]
    document['resources'][0]['content']['style'] = 'missing-style'
    document['references'].append({'key': 'missing-style', 'kind': 'style', 'name': 'Other Library style'})
    local = create(client, name='Local style')
    result = imported(client, document, {'model-1': None, 'missing-style': local['id']})
    resource = result['resources'][0]
    assert resource['content']['style'] == local['id'] and resource['content']['steps'][0]['profile_id'] is None


def test_table_mapping_requires_same_table_and_supports_current_version(client):
    with client.app.state.database.connect() as connection:
        rows = [dict(row) for row in connection.execute('SELECT * FROM roll_tables LIMIT 2')]
    recipe = create(client, 'recipe', {'randomness': {'table_versions': {rows[0]['id']: rows[0]['version_id']}}})
    document = exported(client, recipe)
    key = document['references'][0]['key']
    assert not proposed(client, document, {key: rows[1]['version_id']})['can_import']
    result = imported(client, document, {key: None})
    assert result['resources'][0]['content']['randomness']['table_versions'] == {rows[0]['id']: rows[0]['version_id']}


@pytest.mark.parametrize('change', ['schema', 'duplicate', 'missing-style', 'unrelated', 'invalid-variable', 'empty-name'])
def test_invalid_bundles_are_rejected_before_writes(client, change):
    recipe, _, _ = fixture(client)
    document = exported(client, recipe)
    if change == 'schema':
        document['version'] = 999
    elif change == 'duplicate':
        document['resources'].append(deepcopy(document['resources'][0]))
    elif change == 'missing-style':
        document['resources'].pop()
    elif change == 'unrelated':
        item = deepcopy(document['resources'][1])
        item['key'] = 'not-a-dependency'
        document['resources'].append(item)
    elif change == 'empty-name':
        document['resources'][0]['name'] = '   '
    else:
        document['resources'][0]['content']['instructions'] = '{{undeclared}}'
    before = client.get('/api/writing-resources').json()
    response = client.post('/api/writing-bundles/preview', json={'document': document})
    assert response.status_code == 400, response.text
    assert client.get('/api/writing-resources').json() == before


def test_v38_upgrade_and_extras_links_are_strict(client, story):
    _, archive = backup(client, story)
    legacy = {**archive, 'version': 38, 'data': {key: archive['data'][key] for key in V38_TABLES}}
    assert client.post('/api/archives/imports', json={'content': json.dumps(legacy)}).status_code == 201
    legacy['data']['writing_extras'] = []
    assert client.post('/api/archives/imports', json={'content': json.dumps(legacy)}).status_code == 400
    archive['data']['writing_extras'] = [{'version_id': 'missing', 'content': '{}'}]
    assert client.post('/api/archives/imports', json={'content': json.dumps(archive)}).status_code == 400


def test_first_development_receipt_and_v38_archive_restore_without_rewriting(client, story, monkeypatch):
    from server.writing import context
    original = context.resolve
    def first_format(*args, **kwargs):
        result = original(*args, **kwargs)
        result['version'] = 1
        result.pop('variables')
        result.pop('disabled_baseline')
        return result
    monkeypatch.setattr(context, 'resolve', first_format)
    make_profile(client, 'Legacy development writer', primary=True)
    style = create(client)
    recipe = create(client, 'recipe', {'style': style['id'], 'instructions': '{{count}} {{focus}}',
        'variables': [{'name': 'count', 'label': 'Count', 'type': 'number'}, {'name': 'focus', 'label': 'Focus'}]})
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 0,
        'writing': {'recipe': recipe['id'], 'variables': {'count': 3, 'focus': '{{literal}}'}}})
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    _, document = backup(client, story)
    document['version'] = 38
    document['data'] = {key: document['data'][key] for key in V38_TABLES}
    upload = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert upload.status_code == 201, upload.text
    _, mapping = restore(client, upload.json())
    saved = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert saved['snapshot']['content'] == provider.calls[0][2]
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)
    assert len(provider.calls) == 1
