import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import V42_TABLES
from server.library_formats.files import SourceFiles
from server.lore.files import EntryFiles
from tests.test_archives import backup, restore
from tests.test_library import with_book
from tests.test_text_edits import apply, proposal, target, undo
from tests.test_writing_resources import create, pins, preview


def asset(client, kind='character'):
    content = {'text': 'Original overview.', 'voice': 'Spare.', 'pronouns': 'she/her',
               'greetings': [{'id': 'door', 'label': 'At the door', 'text': 'Welcome.'}]}
    if kind == 'lorebook':
        content = {'text': 'Original overview.', 'lore_definition': {'entries': [
            {'id': 'orchard', 'title': 'Orchard', 'text': 'Old trees.', 'activation': 'always'}]}}
    response = client.post('/api/library', json={'kind': kind, 'name': 'A shared resource', 'content': content})
    assert response.status_code == 201, response.text
    return response.json()


def field_target(client, story, resource, field='text', item=None, kind='library-field'):
    return target(client, {'kind': kind, 'story_id': story['story_id'], 'asset_id': resource['asset_id'],
                          'field': field, **({'item_id': item} if item else {})})


@pytest.mark.parametrize('field,item', [(key, None) for key in ('text', 'voice', 'behavior_rules', 'scenario', 'example_dialogue', 'author_notes', 'pronouns', 'address')] + [('greeting', 'door')])
def test_character_field_publishes_exact_text_and_undo_preserves_other_later_fields(client, story, field, item):
    initial = asset(client)
    before = field_target(client, story, initial, field, item)
    receipt = apply(client, proposal(client, before, ' New 🦉 words.\n'))
    versions = client.get(f"/api/library/{initial['asset_id']}/versions").json()
    assert len(versions) == 2 and versions[1]['content'] == initial['content']
    current = versions[0]
    response = client.post(f"/api/library/{initial['asset_id']}/versions", json={
        'expected_version_id': current['id'], 'name': 'Renamed independently',
        'content': {**current['content'], 'artwork_caption': 'Independent metadata.'}})
    assert response.status_code == 201
    inverse = undo(client, receipt)['receipt']
    final = client.get(f"/api/library/{initial['asset_id']}/versions").json()[0]
    assert inverse['after_target']['text'] == before['text'] and final['name'] == 'Renamed independently'
    assert final['content']['artwork_caption'] == 'Independent metadata.'
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []


@pytest.mark.parametrize('field,item', [('text', None), ('entry', 'orchard')])
def test_canon_publish_checks_external_files_and_retains_rules(client, story, field, item):
    initial = asset(client, 'lorebook')
    before = field_target(client, story, initial, field, item)
    pending = proposal(client, before, '  New trees.\n')
    files = EntryFiles(client.app.state.database, item) if item else SourceFiles(client.app.state.database)
    path = files.working_path(initial['asset_id'], initial['id'])
    original = path.read_bytes()
    path.write_bytes(original + b'\nExternal change.')
    failed = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0})
    assert failed.status_code == 409
    assert len(client.get(f"/api/library/{initial['asset_id']}/versions").json()) == 1
    path.write_bytes(original)
    receipt = apply(client, pending)
    current = client.get(f"/api/library/{initial['asset_id']}/versions").json()[0]
    assert current['content']['lore_definition']['entries'][0]['activation'] == 'always'
    assert target(client, before['ref'])['text'] == '  New trees.\n'
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/text-edit-receipts/{mapping[receipt['id']]}").json()
    assert undo(client, restored)['receipt']['after_target']['text'] == before['text']


@pytest.mark.parametrize('field', ['prose', 'viewpoint', 'tense', 'dialogue', 'rhythm', 'description', 'avoid'])
def test_style_edits_keep_samples_pins_and_other_fields(client, story, field):
    initial = create(client, content={'prose': 'Spare.', 'examples': [{'label': 'Sample', 'text': '  Keep exactly.\n'}]})
    pins(client, story, initial['id'])
    other = client.post('/api/stories', json={'title': 'Second'}).json()
    pins(client, other, initial['id'])
    before = field_target(client, story, initial, field, kind='writing-field')
    receipt = apply(client, proposal(client, before, '  Changed guidance.\n'))
    current = client.get(f"/api/writing-resources/{initial['asset_id']}/versions").json()[0]
    assert current['content']['examples'] == initial['content']['examples']
    assert preview(client, story)['style']['id'] == initial['id'] and preview(client, other)['style']['id'] == initial['id']
    assert undo(client, receipt)['receipt']['after_target']['text'] == before['text']


@pytest.mark.parametrize('field,item', [('instructions', None), ('step-instructions', 'revision')])
def test_recipe_instructions_validate_variables_and_retain_settings(client, story, field, item):
    initial = create(client, 'recipe', {'purpose': 'revise', 'steps': [{'task': 'revision', 'instructions': 'Retain facts.'}],
        'variables': [{'name': 'focus', 'label': 'Focus'}], 'instructions': 'Use {{focus}}.', 'disabled_tasks': ['writer']})
    before = field_target(client, story, initial, field, item, kind='writing-field')
    pending = proposal(client, before, 'Undeclared {{wrong}}.')
    response = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0})
    assert response.status_code == 400 and target(client, before['ref']) == before
    receipt = apply(client, proposal(client, before, '  Refine {{focus}}.\n'))
    current = client.get(f"/api/writing-resources/{initial['asset_id']}/versions").json()[0]
    assert current['content']['purpose'] == 'revise' and current['content']['disabled_tasks'] == ['writer']
    file, document = backup(client, story)
    assert len(document['data']['writing_versions']) == 2
    _, mapping = restore(client, file)
    restored = client.get(f"/api/text-edit-receipts/{mapping[receipt['id']]}").json()
    assert undo(client, restored)['status'] == 'applied'


def prompt_target(client, story, scope='story', key='writer'):
    response = client.post('/api/text-targets/catalog', json={'kind': 'prompt', 'story_id': story['story_id'], 'prompt_scope': scope, 'prompt_key': key})
    assert response.status_code == 200, response.text
    return target(client, response.json()['options'][0]['ref'])


@pytest.mark.parametrize('scope', ['story', 'workspace'])
def test_prompt_scope_restore_and_undo_keep_unrelated_configuration(client, story, scope):
    source = prompt_target(client, story, scope)
    before_workspace = client.get('/api/prompts').json()
    receipt = apply(client, proposal(client, source, '  Write carefully.\n'))
    assert target(client, source['ref'])['text'] == '  Write carefully.\n'
    if scope == 'story':
        assert client.get('/api/prompts').json() == before_workspace
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/text-edit-receipts/{mapping[receipt['id']]}").json()
    if scope == 'workspace':
        response = client.post(f"/api/text-edit-receipts/{restored['id']}/undo", json={'operation_id': uuid4().hex})
        assert response.status_code == 409 and 'restored from an archive' in response.text
        assert target(client, source['ref'])['text'] == '  Write carefully.\n'
    else:
        assert undo(client, restored)['receipt']['after_target']['text'] == source['text']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    _, again = restore(client, second)
    replay = client.get(f"/api/text-edit-receipts/{again[restored['id']]}").json()
    assert replay['before_target']['text'] == source['text'] and replay['after_target']['text'] == '  Write carefully.\n'
    assert undo(client, receipt)['receipt']['after_target']['text'] == source['text']


def test_forbidden_targets_stale_versions_and_archive_tampering(client, story):
    initial = asset(client)
    before = field_target(client, story, initial)
    assert client.post('/api/text-targets/read', json={'target': {**before['ref'], 'field': 'artwork_sha256'}}).status_code == 400
    assert client.post('/api/text-targets/read', json={'target': {**before['ref'], 'item_id': 'extra'}}).status_code == 422
    pending = proposal(client, before, 'Changed.')
    newer = apply(client, proposal(client, before, 'Other author edit.'))
    assert client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0}).status_code == 409
    assert client.post('/api/text-targets/catalog', json={'kind': 'prompt', 'story_id': story['story_id'], 'prompt_key': 'library-assist', 'prompt_scope': 'story'}).status_code == 400
    file, document = backup(client, story)
    bad = deepcopy(document)
    row = next(item for item in bad['data']['asset_versions'] if item['id'] == newer['result']['version_id'])
    row['content'] = json.dumps({**json.loads(row['content']), 'voice': 'Outside the reviewed target.'})
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400
    _, mapping = restore(client, file)
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    assert restore(client, second)


def test_v42_upgrade_keeps_original_destination_set(client, story):
    file, document = backup(client, story)
    document['version'] = 42
    document['data'] = {key: document['data'][key] for key in V42_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 201
    initial = asset(client)
    proposal(client, field_target(client, story, initial), 'Changed.')
    _, document = backup(client, story)
    document['version'] = 42
    document['data'] = {key: document['data'][key] for key in V42_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


def test_library_publication_keeps_two_story_manifests_and_prompt_scopes_independent(client):
    initial = asset(client)
    a, b = with_book(client, initial, 'A'), with_book(client, initial, 'B')
    before = [client.get(f"/api/stories/{item['story_id']}").json() for item in (a, b)]
    apply(client, proposal(client, field_target(client, a, initial, 'voice'), 'New voice.'))
    for item, prior in zip((a, b), before, strict=True):
        after = client.get(f"/api/stories/{item['story_id']}").json()
        assert after['manifest_id'] == prior['manifest_id'] and after['revision'] == prior['revision']
        assert after['attachments'][0]['version_id'] == initial['id']
    first = apply(client, proposal(client, prompt_target(client, a), 'Pinned A instructions.'))
    workspace = apply(client, proposal(client, prompt_target(client, b, 'workspace'), 'New inherited instructions.'))
    assert prompt_target(client, a)['text'] == 'Pinned A instructions.'
    assert prompt_target(client, b)['text'] == 'New inherited instructions.'
    assert undo(client, workspace)['status'] == 'applied'
    assert prompt_target(client, a)['text'] == first['after_target']['text']


def test_restored_pending_workspace_proposal_cannot_bind_to_host_defaults(client, story):
    source = prompt_target(client, story, 'workspace')
    pending = proposal(client, source, 'Pending global instructions.')
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/text-edits/{mapping[pending['id']]}").json()
    attempt = client.post(f"/api/text-edits/{restored['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0})
    assert attempt.status_code == 409 and target(client, source['ref']) == source
    fresh = prompt_target(client, {'story_id': mapping[story['story_id']]}, 'workspace')
    rebase = client.post(f"/api/text-edits/{restored['id']}/rebase", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'target': fresh['ref'], 'expected_version': fresh['version'],
        'selection': {'start': 0, 'end': len(fresh['text']), 'text': fresh['text']}, 'action': 'update', 'replacement': 'Retargeted.'})
    assert rebase.status_code == 400
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    _, again = restore(client, second)
    replay = client.post(f"/api/text-edits/{again[restored['id']]}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0})
    assert replay.status_code == 409


def test_writing_field_preserves_inert_extensions_and_conflicting_undo(client, story):
    response = client.post('/api/writing-resources', json={'operation_id': uuid4().hex, 'kind': 'style', 'name': 'Extended style',
        'content': {'prose': 'Plain.'}, 'unsupported': {'future_guidance': {'enabled': True}}})
    assert response.status_code == 201, response.text
    initial = response.json()
    source = field_target(client, story, initial, 'prose', kind='writing-field')
    receipt = apply(client, proposal(client, source, 'New.'))
    apply(client, proposal(client, target(client, source['ref']), 'Newer independent text.'))
    result = undo(client, receipt)
    assert result['status'] == 'conflict' and target(client, source['ref'])['text'] == 'Newer independent text.'
    current = client.get(f"/api/writing-resources/{initial['asset_id']}/versions").json()[0]
    assert current['unsupported'] == initial['unsupported']
    file, _ = backup(client, story)
    assert restore(client, file)
