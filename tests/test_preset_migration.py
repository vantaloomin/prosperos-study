import base64
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.format import ARCHIVE_VERSION, V52_TABLES
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.main import create_app
from server.migration.preset_conversion import literal_instructions
from server.writing.variables import render
from tests.test_archives import backup, restore
from tests.test_profiles import MemoryVault, make_profile
from tests.test_writing_resources import pins


def source(**overrides):
    return json.dumps({'name': 'Quiet preset', 'temperature': 0.6, 'openai_max_tokens': 900,
                       'prompts': [{'name': 'Voice', 'content': 'Stay with {{char}}. {{selection}}'},
                                   {'name': 'Unselected', 'content': 'DO NOT ACCEPT'}],
                       'reverse_proxy': 'https://foreign.invalid', 'openai_model': 'foreign-model', **overrides}).encode()


def stage(client, raw=None):
    response = client.post('/api/migration/presets', json={'filename': 'quiet.json', 'source_base64': base64.b64encode(raw or source()).decode()})
    assert response.status_code == 201, response.text
    return response.json()


def body(preview, **overrides):
    return {'operation_id': uuid4().hex, 'source_sha256': preview['source_sha256'], 'reviewed': True,
            'name': 'Reviewed voice', 'instructions': 'Stay with {{char}}. {{selection}}', 'instruction_keys': ['prompts[0]'], **overrides}


def publish(client, preview, payload=None):
    response = client.post(f"/api/migration/presets/{preview['id']}/publish", json=payload or body(preview))
    assert response.status_code == 201, response.text
    return response.json()


def test_stage_and_publish_require_selection_without_activation(client, story):
    preview = stage(client)
    assert client.get('/api/writing-resources').json() == []
    assert client.get(f"/api/migration/presets/{preview['id']}/original").content == source()
    assert client.get(f"/api/migration/presets/{preview['id']}/report").json()['format'] == 'sillytavern-chat-preset'
    before = client.get(f"/api/stories/{story['story_id']}").json()
    result = publish(client, preview)
    resource = result['resource']
    assert resource['content']['instructions'] == literal_instructions('Stay with {{char}}. {{selection}}')
    assert render(resource['content']['instructions'], {}) == 'Stay with {{char}}. {{selection}}'
    assert resource['content']['steps'] == [] and resource['content']['randomness'] is None
    assert 'DO NOT ACCEPT' not in encode(resource) and 'foreign.invalid' not in encode(resource)
    assert result['profile'] is None and client.get('/api/profiles').json()['profiles'] == []
    assert client.get(f"/api/stories/{story['story_id']}").json() == before
    origins = client.get(f"/api/writing-versions/{resource['id']}/imports").json()
    assert origins[0]['receipt']['instruction_keys'] == ['prompts[0]']
    with client.app.state.database.connect() as connection:
        for table in ('recipe_runs', 'generations', 'writing_pins'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_sampling_preview_then_separate_copy_preserves_primary_credentials_and_base(client):
    client.app.state.vault = MemoryVault()
    base = client.post('/api/profiles', json={'name': 'My writer', 'make_primary': True, 'api_key': 'local-test-key',
                                           'config': {'provider': 'openai', 'model': 'test-model', 'temperature': 0.2}}).json()
    preview = stage(client)
    selection = {'sampling_keys': ['temperature', 'max_output_tokens'], 'base_profile_id': base['profile_id'], 'expected_profile_version_id': base['id']}
    proposal = client.post(f"/api/migration/presets/{preview['id']}/configuration-preview", json=selection).json()
    assert proposal['changes'] == [{'field': 'temperature', 'before': 0.2, 'after': 0.6}, {'field': 'max_output_tokens', 'before': 1200, 'after': 900}]
    assert len(client.get('/api/profiles').json()['profiles']) == 1
    copied = publish(client, preview, body(preview, **selection))['profile']
    assert copied['profile_id'] != base['profile_id'] and not copied['has_saved_key']
    assert copied['config'] == {**base['config'], 'temperature': 0.6, 'max_output_tokens': 900}
    profiles = client.get('/api/profiles').json()
    assert profiles['primary_profile_id'] == base['profile_id'] and len(profiles['profiles']) == 2
    assert next(row for row in profiles['profiles'] if row['id'] == base['id'])['has_saved_key']
    assert len(client.app.state.vault.values) == 1


@pytest.mark.parametrize('case', ['not-reviewed', 'source', 'fragment', 'duplicate-fragment', 'unknown-sampler', 'duplicate-sampler', 'no-profile', 'stale-profile', 'unsupported-profile', 'unused-profile'])
def test_invalid_review_cannot_publish_or_mutate_profiles(client, case):
    base = client.post('/api/profiles', json={'name': 'CLI', 'config': {'provider': 'codex', 'model': 'test'}}).json()
    preview = stage(client)
    changes = {
        'not-reviewed': {'reviewed': False}, 'source': {'source_sha256': '0' * 64},
        'fragment': {'instruction_keys': ['missing']}, 'duplicate-fragment': {'instruction_keys': ['prompts[0]'] * 2},
        'unknown-sampler': {'sampling_keys': ['seed']}, 'duplicate-sampler': {'sampling_keys': ['temperature'] * 2},
        'no-profile': {'sampling_keys': ['temperature']},
        'stale-profile': {'sampling_keys': ['temperature'], 'base_profile_id': base['profile_id'], 'expected_profile_version_id': 'stale'},
        'unsupported-profile': {'sampling_keys': ['temperature'], 'base_profile_id': base['profile_id'], 'expected_profile_version_id': base['id']},
        'unused-profile': {'base_profile_id': base['profile_id'], 'expected_profile_version_id': base['id']},
    }
    response = client.post(f"/api/migration/presets/{preview['id']}/publish", json=body(preview, **changes[case]))
    assert response.status_code in (400, 409, 422), response.text
    assert client.get('/api/writing-resources').json() == []
    assert len(client.get('/api/profiles').json()['profiles']) == 1


def test_exact_and_proposal_duplicates_default_skip_but_names_do_not_identify(client):
    first = stage(client)
    created = publish(client, first)['resource']
    exact = stage(client)
    assert exact['duplicates'][0]['match'] == 'exact-source'
    assert publish(client, exact)['status'] == 'skipped'
    equivalent = stage(client, source(reverse_proxy='https://other.invalid'))
    assert equivalent['duplicates'][0]['match'] == 'proposal-content'
    assert publish(client, equivalent)['status'] == 'skipped'
    assert publish(client, equivalent, body(equivalent, duplicate_action='new'))['resource']['asset_id'] != created['asset_id']
    different = stage(client, source(temperature=0.5))
    assert different['duplicates'] == []
    assert publish(client, different)['status'] == 'imported'


def test_operation_retries_and_explicit_current_identity_version_updates(client):
    preview = stage(client)
    payload = body(preview)
    original = publish(client, preview, payload)
    assert publish(client, preview, payload) == original
    endpoint = f"/api/migration/presets/{preview['id']}/publish"
    assert client.post(endpoint, json={**payload, 'name': 'Changed'}).status_code == 409
    asset = original['resource']
    update = body(preview, target_asset_id=asset['asset_id'], expected_version_id=asset['id'], instructions='An author correction.')
    revised = publish(client, preview, update)['resource']
    assert revised['number'] == 2 and revised['asset_id'] == asset['asset_id']
    assert client.post(endpoint, json={**update, 'operation_id': uuid4().hex}).status_code == 409
    versions = client.get(f"/api/writing-resources/{asset['asset_id']}/versions").json()
    assert len(versions) == 2 and versions[1]['content'] == asset['content']


def test_preset_origins_profile_snapshots_and_exact_bytes_restore_fresh(client, tmp_path):
    base = make_profile(client, 'Local', primary=True)
    preview = stage(client)
    result = publish(client, preview, body(preview, sampling_keys=['temperature'], base_profile_id=base['profile_id'], expected_profile_version_id=base['id']))
    _, document = backup(client)
    assert document['version'] == ARCHIVE_VERSION
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        staged = fresh.post('/api/archives/imports', json={'content': encode(document)})
        assert staged.status_code == 201, staged.text
        _, mapping = restore(fresh, staged.json())
        saved = fresh.get(f"/api/writing-versions/{mapping[result['resource']['id']]}/imports").json()[0]
        assert saved['profile_id'] == mapping[result['profile']['profile_id']]
        assert saved['profile_version_id'] == mapping[result['profile']['id']]
        assert fresh.get(f"/api/migration/presets/{saved['import_id']}/original").content == source()
        _, restored = backup(fresh)
        assert decode(restored['data']['preset_origins'][0]['receipt']) == decode(document['data']['preset_origins'][0]['receipt'])
        assert stage(fresh)['duplicates']
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as restarted:
        assert len(restarted.get('/api/writing-resources').json()) == 1
        assert restarted.get(f"/api/migration/presets/{saved['import_id']}/original").content == source()


@pytest.mark.parametrize('damage', ['source', 'conversion', 'instructions', 'selection', 'config', 'before', 'base', 'extras'])
def test_archive_rejects_mismatched_preset_receipts(client, damage):
    base = make_profile(client, 'Local')
    preview = stage(client)
    publish(client, preview, body(preview, sampling_keys=['temperature'], base_profile_id=base['profile_id'], expected_profile_version_id=base['id']))
    _, document = backup(client)
    imported, origin = document['data']['preset_imports'][0], document['data']['preset_origins'][0]
    receipt = decode(origin['receipt'])
    if damage == 'source':
        imported['source_base64'] = base64.b64encode(source(temperature=0.4)).decode()
    elif damage == 'conversion':
        conversion = decode(imported['conversion'])
        conversion['name'] = 'Tampered'
        imported['conversion'] = encode(conversion)
    elif damage == 'instructions':
        receipt['instructions'] = 'Tampered'
    elif damage == 'selection':
        receipt['instruction_keys'] = ['missing']
    elif damage == 'config':
        origin['configuration'] = '{}'
    elif damage == 'before':
        receipt['configuration_changes'][0]['before'] = 0.33
    elif damage == 'base':
        origin['base_profile_id'] = origin['profile_id']
    else:
        document['data']['writing_extras'][0]['content'] = '{}'
    origin['receipt'] = encode(receipt)
    response = client.post('/api/archives/imports', json={'content': encode(document)})
    assert response.status_code == 400, response.text


def test_format_52_upgrades_and_credential_sources_are_never_preserved(client):
    response = client.post('/api/migration/presets', json={'filename': 'private.json', 'source_base64': base64.b64encode(source(api_key='PRIVATE')).decode()})
    assert response.status_code == 400 and 'PRIVATE' not in response.text
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM preset_imports').fetchone()[0] == 0
    _, document = backup(client)
    legacy = {**document, 'version': 52, 'data': {table: deepcopy(document['data'][table]) for table in V52_TABLES}}
    upgraded = parse_archive(encode(legacy))
    assert upgraded['version'] == ARCHIVE_VERSION and upgraded['data']['preset_imports'] == []


def test_story_archive_keeps_accepted_recipe_origin_and_local_sampling_basis_only(client, story):
    base = make_profile(client, 'Local basis')
    preview = stage(client)
    selected = publish(client, preview, body(preview, sampling_keys=['temperature'], base_profile_id=base['profile_id'], expected_profile_version_id=base['id']))
    other = stage(client, source(name='Outside preset', temperature=0.3))
    outside = publish(client, other, body(other, name='Outside recipe'))
    pins(client, story, recipe=selected['resource']['id'])
    file, document = backup(client, story)
    assert {row['id'] for row in document['data']['profiles']} == {base['profile_id'], selected['profile']['profile_id']}
    assert {row['id'] for row in document['data']['preset_imports']} == {preview['id']}
    assert outside['resource']['id'] not in encode(document)
    _, mapping = restore(client, file)
    _, again = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    assert len(again['data']['preset_imports']) == 1
