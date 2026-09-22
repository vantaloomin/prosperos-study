import base64
import json
import sqlite3
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.database import encode
from server.main import create_app
from tests.test_archives import backup, restore
from tests.test_card_markdown import card
from tests.test_character_containers import byaf_members, charx_members, zipped
from tests.test_library_imports import publish_body
from tests.test_native_imports import BOOKS
from tests.test_preset_migration import body as preset_body
from tests.test_preset_migration import source as preset_source
from tests.test_transcript_migration import body as transcript_body
from tests.test_transcript_migration import st_source
from tests.test_writing_bundles import exported
from tests.test_writing_resources import create, pins


def upload(filename, source):
    return {'filename': filename, 'source_base64': base64.b64encode(source).decode()}


def stage(client, files, operation=None):
    response = client.post('/api/migration/batches', json={'operation_id': operation or uuid4().hex, 'files': files})
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, item):
    response = client.get(f"/api/migration/batch-items/{item['id']}/preview")
    assert response.status_code == 200, response.text
    return response.json()


def publish(client, item, choices):
    response = client.post(f"/api/migration/batch-items/{item['id']}/publish", json={'expected_revision': item['revision'], 'choices': choices})
    assert response.status_code == 201, response.text
    return response.json()


def test_mixed_batch_detection_error_isolation_exact_sources_and_no_publication(client):
    files = [upload('chat.jsonl', st_source()), upload('hero.charx', zipped(charx_members())), upload('preset.json', preset_source()),
             upload('duplicate.jsonl', st_source()), upload('broken.json', b'{invalid'), upload('scene.md', b'Alice: Hello\nBob: Welcome')]
    operation = uuid4().hex
    batch = stage(client, files, operation)
    assert [row['status'] for row in batch['items']] == ['review', 'review', 'review', 'review', 'rejected', 'choose']
    assert [row['kind'] for row in batch['items'][:4]] == ['transcript', 'library', 'preset', 'transcript']
    assert batch['items'][3]['batch_duplicates'][0]['match'] == 'exact-source'
    assert set(batch['items'][5]['candidates']) == {'library', 'transcript'}
    assert stage(client, files, operation) == batch
    for row, file in zip(batch['items'], files, strict=True):
        response = client.get(f"/api/migration/batch-items/{row['id']}/original")
        assert response.status_code == (404 if row['status'] == 'rejected' else 200)
        if row['status'] != 'rejected':
            assert response.content == base64.b64decode(file['source_base64'])
    assert client.get('/api/stories').json() == client.get('/api/library').json() == client.get('/api/writing-resources').json() == []
    assert client.get('/api/migration/batches').json()[0]['items'] == 6


def test_signature_detection_does_not_trust_misleading_extensions(client):
    files = [upload('role-messages.card', b'[{"role":"user","content":"Literal words"}]'), upload('picture.txt', zipped(charx_members())),
             upload('settings.anything', preset_source())]
    batch = stage(client, files)
    assert [row['kind'] for row in batch['items']] == ['transcript', 'library', 'preset']
    assert all(row['status'] == 'review' for row in batch['items'])
    assert preview(client, batch['items'][0])['messages'][0]['variants'] == ['Literal words']


def test_existing_character_and_world_info_dialects_share_the_mixed_queue(client):
    documents = [card(version) for version in ('v1', 'v2', 'v3')]
    documents += [{'char_name': 'Same name', 'char_persona': 'Different prose.'},
                  {'aiName': 'Same name', 'aiPersona': 'Another original.'}]
    documents += list(BOOKS.values())
    documents += [{**BOOKS['novelai-lorebook'], 'lorebookVersion': version} for version in (3, 4, 5)]
    files = [upload(f'variant-{index}.json', json.dumps(value).encode()) for index, value in enumerate(documents)]
    files += [upload('rich.byaf', zipped(byaf_members()))]
    batch = stage(client, files)
    assert len(batch['items']) == 14
    assert all(item['kind'] == 'library' and item['status'] == 'review' for item in batch['items'])
    assert not batch['items'][4]['batch_duplicates']  # Equal names do not make equal proposals.
    for item in batch['items']:
        assert preview(client, item)['drafts']
    assert client.get('/api/library').json() == []


def test_choose_correct_skip_resume_and_stale_queue_revision(client):
    batch = stage(client, [upload('scene.txt', b'Alice: First\nBob: Second')])
    item = batch['items'][0]
    endpoint = f"/api/migration/batch-items/{item['id']}"
    assert client.get(endpoint + '/preview').status_code == 409
    assert client.post(endpoint + '/interpretation', json={'expected_revision': item['revision'], 'kind': 'preset'}).status_code == 400
    selected = client.post(endpoint + '/interpretation', json={'expected_revision': item['revision'], 'kind': 'transcript'}).json()['items'][0]
    assert selected['kind'] == 'transcript' and selected['status'] == 'review'
    assert all(message['proposed_role'] == 'skip' for message in preview(client, selected)['messages'])
    assert client.put(endpoint + '/selection', json={'expected_revision': item['revision'], 'skipped': True}).status_code == 409
    skipped = client.put(endpoint + '/selection', json={'expected_revision': selected['revision'], 'skipped': True}).json()['items'][0]
    assert skipped['status'] == 'omitted'
    resumed = client.put(endpoint + '/selection', json={'expected_revision': skipped['revision'], 'skipped': False}).json()['items'][0]
    assert resumed['status'] == 'review' and resumed['import_id'] == selected['import_id']


def adopt_reviewed_resources(client, outcomes):
    story = outcomes[0]['result']
    versions = outcomes[1]['result']['versions']
    recipe = outcomes[2]['result']['resource']
    before = client.get(f"/api/branches/{story['branch_id']}").json()['messages']
    detail = client.get(f"/api/stories/{story['story_id']}").json()
    assert detail['attachments'] == []
    character = next(row for row in versions if row['kind'] == 'character')
    response = client.put(f"/api/stories/{story['story_id']}/attachments", json={
        'operation_id': uuid4().hex, 'expected_revision': detail['revision'],
        'attachments': [{'asset_id': character['asset_id'], 'version_id': character['id']}]})
    assert response.status_code == 200, response.text
    adopted = client.get(f"/api/stories/{story['story_id']}").json()['attachments']
    assert {row['version_id'] for row in adopted} == {row['id'] for row in versions}
    pins(client, story, recipe=recipe['id'])
    # Publishing another recipe version must not change this deliberate pin.
    response = client.post(f"/api/writing-resources/{recipe['asset_id']}/versions", json={
        'operation_id': uuid4().hex, 'kind': 'recipe', 'name': 'Later revision',
        'expected_version_id': recipe['id'], 'content': {'instructions': 'Later guidance.'}})
    assert response.status_code == 201, response.text
    assert client.get(f"/api/stories/{story['story_id']}/writing-preferences").json()['recipe'] == recipe['id']
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == before


def test_combined_foreign_imports_duplicates_receipts_and_fresh_archive_restore(client, tmp_path):
    raw_card = zipped(charx_members())
    files = [upload('chat.jsonl', st_source()), upload('hero.charx', raw_card), upload('preset.json', preset_source()), upload('same.jsonl', st_source())]
    batch = stage(client, files)
    choices = [transcript_body(preview(client, batch['items'][0])), publish_body(preview(client, batch['items'][1])),
               preset_body(preview(client, batch['items'][2])), transcript_body(preview(client, batch['items'][3]))]
    outcomes = [publish(client, item, choice) for item, choice in zip(batch['items'], choices, strict=True)]
    assert outcomes[3]['result']['status'] == 'skipped'
    assert publish(client, batch['items'][0], choices[0]) == outcomes[0]
    assert len(client.get('/api/stories').json()) == 1
    assert len(client.get('/api/library').json()) == 2 and len(client.get('/api/writing-resources').json()) == 1
    assert client.get(f"/api/migration/batches/{batch['id']}").json()['items'][3]['status'] == 'complete'
    for item in outcomes:
        report = client.get(f"/api/migration/batch-items/{item['id']}/report").json()
        assert report['result'] == item['result'] and report['publication']
    with client.app.state.database.connect() as connection:
        for table in ('generations', 'recipe_runs', 'summary_pending', 'relationship_jobs'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    adopt_reviewed_resources(client, outcomes)
    story_id = outcomes[0]['result']['story_id']
    recipe_id = outcomes[2]['result']['resource']['id']
    with TestClient(create_app(tmp_path / 'test.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as restarted:
        assert restarted.get(f'/api/stories/{story_id}/writing-preferences').json()['recipe'] == recipe_id
        assert len(restarted.get(f'/api/stories/{story_id}').json()['attachments']) == 2
    _, archive = backup(client)
    assert 'migration_batch_items' not in archive['data']
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        staged = fresh.post('/api/archives/imports', json={'content': encode(archive)}).json()
        _, mapping = restore(fresh, staged)
        for kind, item, raw in zip(('transcripts', 'library-imports', 'presets'), batch['items'][:3], (st_source(), raw_card, preset_source()), strict=True):
            root = '/api/library-imports' if kind == 'library-imports' else '/api/migration/' + kind
            assert fresh.get(f"{root}/{mapping[item['import_id']]}/original").content == raw
        restored_story = outcomes[0]['result']
        nodes = fresh.get(f"/api/branches/{mapping[restored_story['branch_id']]}").json()['messages']
        assert [node['text'] for node in nodes] == ['  The gate opens.\n', 'Chosen reply ☂ <script>literal</script>']
        assert fresh.get(f'/api/stories/{mapping[story_id]}/writing-preferences').json()['recipe'] == mapping[recipe_id]
        attachments = fresh.get(f'/api/stories/{mapping[story_id]}').json()['attachments']
        assert {row['version_id'] for row in attachments} == {mapping[row['id']] for row in outcomes[1]['result']['versions']}
        assert fresh.get('/api/migration/batches').json() == []
        backup(fresh)


def test_interrupted_response_retries_frozen_choices_without_republishing(client, monkeypatch, tmp_path):
    import server.migration.batch_publication as publication
    batch = stage(client, [upload('chat.jsonl', st_source())])
    item = batch['items'][0]
    choices = transcript_body(preview(client, item))
    real_publish = publication.publish_item
    calls = []
    def interrupted(database, row, body):
        calls.append(row['id'])
        real_publish(database, row, body)
        raise RuntimeError('Simulated interruption after commit, before queue receipt')
    monkeypatch.setattr(publication, 'publish_item', interrupted)
    endpoint = f"/api/migration/batch-items/{item['id']}"
    response = client.post(endpoint + '/publish', json={'expected_revision': item['revision'], 'choices': choices})
    assert response.status_code == 503 and len(client.get('/api/stories').json()) == 1
    frozen = client.get(f"/api/migration/batches/{batch['id']}").json()['items'][0]
    assert frozen['status'] == 'publishing'
    altered = {**choices, 'title': 'Do not accept'}
    assert client.post(endpoint + '/publish', json={'expected_revision': frozen['revision'], 'choices': altered}).status_code == 409
    with TestClient(create_app(tmp_path / 'test.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as restarted:
        assert restarted.get(f"/api/migration/batches/{batch['id']}").json()['items'][0]['status'] == 'publishing'
        response = restarted.post(endpoint + '/retry', json={'expected_revision': frozen['revision']})
        assert response.status_code == 201, response.text
        assert response.json()['status'] == 'complete'
        assert len(restarted.get('/api/stories').json()) == 1 and calls == [item['id']]


def test_invalid_choice_can_be_corrected_without_a_successful_receipt(client):
    batch = stage(client, [upload('chat.jsonl', st_source())])
    item = batch['items'][0]
    choices = transcript_body(preview(client, item), selections=[{'index': 0, 'variant': 0, 'role': 'assistant'}])
    response = client.post(f"/api/migration/batch-items/{item['id']}/publish", json={'expected_revision': item['revision'], 'choices': choices})
    assert response.status_code == 400
    current = client.get(f"/api/migration/batches/{batch['id']}").json()['items'][0]
    assert current['status'] == 'review' and current['error'] and current['result'] is None
    assert publish(client, current, transcript_body(preview(client, current)))['status'] == 'complete'


def test_native_archive_and_writing_bundle_keep_existing_review_contracts(client, story):
    _, document = backup(client, story)
    resource = create(client, 'recipe', {'instructions': 'Reviewed native guidance.'})
    bundle = exported(client, resource)
    sources = [json.dumps(document, indent=2).encode(), json.dumps(bundle, indent=3).encode()]
    batch = stage(client, [upload('native.json', sources[0]), upload('recipe.json', sources[1])])
    assert [item['kind'] for item in batch['items']] == ['archive', 'writing-bundle']
    archive_item, bundle_item = batch['items']
    archive_preview = preview(client, archive_item)
    bundle_preview = preview(client, bundle_item)
    assert bundle_preview['can_import'] and archive_preview['summary']['stories'][0]['id'] == story['story_id']
    restored = publish(client, archive_item, {'sha256': archive_preview['sha256']})
    imported = publish(client, bundle_item, {'mappings': {}, 'preview_fingerprint': bundle_preview['fingerprint']})
    assert restored['result']['story_ids'][0] != story['story_id']
    assert imported['result']['resources'][0]['content'] == resource['content']
    for item, source in zip(batch['items'], sources, strict=True):
        assert client.get(f"/api/migration/batch-items/{item['id']}/original").content == source
    duplicates = stage(client, [upload('native.json', sources[0]), upload('recipe.json', sources[1])])
    for item in duplicates['items']:
        report = preview(client, item)
        choices = {'sha256': report['sha256']} if item['kind'] == 'archive' else {'mappings': {}, 'preview_fingerprint': report['fingerprint']}
        assert publish(client, item, choices)['result']['status'] == 'skipped'
    assert len(client.get('/api/stories').json()) == 2 and len(client.get('/api/writing-resources').json()) == 2


@pytest.mark.parametrize('raw', [b'{"format":[],"bad":true}', b'\xff', b'{"role":', b'{"x":NaN}'])
def test_malformed_content_is_rejected_individually(client, raw):
    batch = stage(client, [upload('bad.json', raw), upload('valid.json', preset_source())])
    assert batch['items'][0]['status'] == 'rejected' and batch['items'][1]['status'] == 'review'


def test_credential_rejection_never_retains_original_input(client):
    batch = stage(client, [upload('private.json', preset_source(api_key='NEVER_STORE_THIS')), upload('valid.json', preset_source())])
    assert batch['items'][0]['status'] == 'rejected'
    with client.app.state.database.connect() as connection:
        rows = connection.execute('SELECT source_base64,candidates,error FROM migration_batch_items').fetchall()
        assert 'NEVER_STORE_THIS' not in encode([dict(row) for row in rows])
        assert rows[0]['source_base64'] == ''


def test_batch_limits_and_stage_operation_conflicts(client):
    files = [upload('scene.txt', b'Words')]
    operation = uuid4().hex
    stage(client, files, operation)
    changed = deepcopy(files)
    changed[0]['filename'] = 'other.txt'
    assert client.post('/api/migration/batches', json={'operation_id': operation, 'files': changed}).status_code == 409
    assert client.post('/api/migration/batches', json={'operation_id': uuid4().hex, 'files': files * 21}).status_code == 422
    assert client.post('/api/migration/batches', json={'operation_id': uuid4().hex, 'files': []}).status_code == 422


def test_oversized_total_is_rejected_before_any_batch_is_stored(client):
    oversized = upload('large.txt', b'x' * (8 * 1024 * 1024 + 1))
    response = client.post('/api/migration/batches', json={'operation_id': uuid4().hex, 'files': [oversized] * 4})
    assert response.status_code == 400 and '32 MiB' in response.text
    assert client.get('/api/migration/batches').json() == []


def test_client_file_read_failure_stays_individual_and_retry_receipts_are_immutable(client):
    failed = {'filename': 'oversized.charx', 'source_base64': '', 'read_error': 'Choose a file no larger than 10 MiB.'}
    batch = stage(client, [failed, upload('good.json', preset_source())])
    assert batch['items'][0]['status'] == 'rejected' and '10 MiB' in batch['items'][0]['error']
    item = batch['items'][1]
    saved = publish(client, item, preset_body(preview(client, item)))
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            connection.execute('UPDATE migration_batch_items SET result=? WHERE id=?', ('{}', saved['id']))
    assert client.get(f"/api/migration/batches/{batch['id']}").json()['items'][1]['result'] == saved['result']


def test_native_recovery_uses_committed_receipt_even_if_staged_archive_file_disappears(client, story, monkeypatch):
    import server.migration.batch_publication as publication
    from server.archives.service import Archives
    _, document = backup(client, story)
    batch = stage(client, [upload('archive.json', encode(document).encode())])
    item = batch['items'][0]
    choices = {'sha256': preview(client, item)['sha256']}
    real = publication.publish_item
    def interrupted(database, row, body):
        result = real(database, row, body)
        assert result['story_ids']
        _, staged_path = Archives(database).file(row['import_id'])
        staged_path.unlink()  # Test-owned temporary archive, after a successful commit.
        raise RuntimeError('Lost response and missing temporary staged file')
    monkeypatch.setattr(publication, 'publish_item', interrupted)
    endpoint = f"/api/migration/batch-items/{item['id']}"
    assert client.post(endpoint + '/publish', json={'expected_revision': item['revision'], 'choices': choices}).status_code == 503
    pending = client.get(f"/api/migration/batches/{batch['id']}").json()['items'][0]
    response = client.post(endpoint + '/retry', json={'expected_revision': pending['revision']})
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'complete' and len(client.get('/api/stories').json()) == 2
