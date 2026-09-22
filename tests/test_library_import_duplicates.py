import json
from copy import deepcopy
from uuid import uuid4

from server.library_formats.import_models import ImportPublish
from server.operations import remember
from tests.test_archives import backup, restore
from tests.test_card_markdown import card
from tests.test_library_imports import publish_body, publish_import, stage


def source(version='v1', **changes):
    value = card(version)
    target = value if version == 'v1' else value['data']
    target.update(changes)
    return json.dumps(value).encode()


def result(client, preview, body=None):
    response = publish_import(client, preview, body)
    assert response.status_code == 201, response.text
    return response.json()


def test_library_exact_source_and_equivalent_proposal_skip_until_deliberate_copy(client):
    preview = stage(client, source())
    assert preview['duplicates'] == []
    first = result(client, preview)['versions'][0]
    exact = stage(client, source())
    assert exact['duplicates'] == [{'part': 'character', 'version_id': first['id'], 'asset_id': first['asset_id'], 'name': first['name'], 'match': 'exact-source'}]
    skipped = result(client, exact)
    assert skipped['versions'] == [] and skipped['skipped'][0]['part'] == 'character'
    changed_metadata = stage(client, source(name='A different label', extensions={'reference': 'OTHER'}))
    assert changed_metadata['duplicates'][0]['match'] == 'proposal-content'
    payload = publish_body(changed_metadata)
    assert result(client, changed_metadata, payload)['versions'] == []
    payload['operation_id'] = uuid4().hex
    payload['choices'][0]['duplicate_action'] = 'new'
    copied = result(client, changed_metadata, payload)
    assert copied['versions'][0]['asset_id'] != first['asset_id']
    assert result(client, changed_metadata, payload) == copied
    assert len(client.get('/api/library').json()) == 2


def test_same_name_different_content_and_unpublished_sources_are_not_duplicates(client):
    first = stage(client, source())
    second = stage(client, source())
    assert second['duplicates'] == []
    result(client, first)
    different = stage(client, source(description='A materially different character.'))
    assert different['duplicates'] == []
    assert len(result(client, different)['versions']) == 1
    assert len(client.get('/api/library').json()) == 2


def test_deduplication_rechecks_at_publish_after_preview(client):
    first, second = stage(client, source()), stage(client, source())
    result(client, first)
    saved = result(client, second)
    assert not saved['versions'] and len(saved['skipped']) == 1


def test_partial_duplicates_publish_only_new_parts_without_implicit_links(client):
    original = stage(client, source('v3'))
    result(client, original)
    changed = stage(client, source('v3', description='A different character with the same imported world.'))
    assert [item['part'] for item in changed['duplicates']] == ['lorebook']
    saved = result(client, changed)
    assert len(saved['versions']) == 1 and saved['versions'][0]['kind'] == 'character'
    assert not saved['versions'][0]['content'].get('lorebook_versions')
    assert [item['part'] for item in saved['skipped']] == ['lorebook']
    value = card('v3')
    value['data']['character_book']['description'] = 'A different world.'
    other = stage(client, json.dumps(value).encode())
    saved = result(client, other)
    assert len(saved['versions']) == 1 and saved['versions'][0]['kind'] == 'lorebook'
    assert [item['part'] for item in saved['skipped']] == ['character']


def test_explicit_update_uses_identity_and_current_version_even_for_duplicate(client):
    preview = stage(client, source())
    old = result(client, preview)['versions'][0]
    payload = publish_body(preview)
    payload['choices'][0].update(target_asset_id=old['asset_id'], expected_version_id=old['id'])
    updated = result(client, preview, payload)
    assert updated['versions'][0]['number'] == 2 and not updated['skipped']
    stale = deepcopy(payload)
    stale['operation_id'] = uuid4().hex
    assert publish_import(client, preview, stale).status_code == 409
    assert len(client.get('/api/library').json()) == 1


def test_pre_deduplication_operation_fingerprint_still_replays(client):
    preview = stage(client, source())
    payload = publish_body(preview)
    body = ImportPublish.model_validate(payload)
    old_payload = {'import_id': preview['id'], **body.model_dump(exclude={'operation_id'})}
    for choice in old_payload['choices']:
        choice.pop('duplicate_action')
    old_result = {'versions': []}
    with client.app.state.database.connect(write=True) as connection:
        remember(connection, body.operation_id, 'library-import', old_payload, old_result)
    assert result(client, preview, payload) == old_result


def test_archive_restore_keeps_import_duplicate_evidence(client):
    preview = stage(client, source('v3'))
    published = result(client, preview)
    file, _ = backup(client)
    _, mapping = restore(client, file)
    again = stage(client, source('v3'))
    assert {mapping[item['id']] for item in published['versions']} <= {item['version_id'] for item in again['duplicates']}
    assert not result(client, again)['versions']
