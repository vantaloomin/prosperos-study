import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import V41_TABLES
from server.database import Database
from server.mechanics.state import node_state
from server.text_edits.models import TextSelection
from server.text_edits.selection import apply_selection, whole_text
from server.text_edits.service import read_receipt
from server.text_edits.targets import snapshot_version
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_passage_revisions import passages, revise
from tests.test_v07_manuscript import book_fixture


def target(client, ref):
    response = client.post('/api/text-targets/read', json={'target': ref})
    assert response.status_code == 200, response.text
    return response.json()


def passage_target(client, story, node_id, branch_id=None):
    return target(client, {'kind': 'passage', 'story_id': story['story_id'], 'branch_id': branch_id or story['branch_id'], 'node_id': node_id})


def proposal(client, source, replacement, selection=None, action='update'):
    body = {'operation_id': uuid4().hex, 'target': source['ref'], 'expected_version': source['version'],
            'selection': selection or whole_text(source['text']), 'action': action, 'replacement': replacement, 'explanation': 'An explicit author edit.'}
    response = client.post('/api/text-edits', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/text-edits', json=body).json() == response.json()
    return response.json()


def apply(client, value):
    body = {'operation_id': uuid4().hex, 'expected_revision': value['revision'], 'branch_name': 'Revised telling', 'acknowledge_state_reset': True}
    endpoint = f"/api/text-edits/{value['id']}/apply"
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert client.post(endpoint, json=body).json() == response.json()
    assert client.post(endpoint, json={**body, 'operation_id': uuid4().hex}).json() == response.json()
    return response.json()


def undo(client, receipt):
    body = {'operation_id': uuid4().hex, 'acknowledge_state_reset': True}
    endpoint = f"/api/text-edit-receipts/{receipt['id']}/undo"
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert client.post(endpoint, json=body).json() == response.json()
    assert client.post(endpoint, json={'operation_id': uuid4().hex, 'acknowledge_state_reset': True}).json()['status'] == response.json()['status']
    return response.json()


def save_document(client, source, text):
    body = {'operation_id': uuid4().hex, 'target': source['ref'], 'expected_version': source['version'], 'text': text}
    response = client.put('/api/text-documents', json=body)
    assert response.status_code == 200, response.text
    assert client.put('/api/text-documents', json=body).json() == response.json()
    return response.json()


@pytest.mark.parametrize('action,start,end,replacement,expected', [
    ('replace', 2, 4, '🕯', 'A 🕯 B'), ('insert-before', 2, 4, 'new ', 'A new 🦉 B'),
    ('insert-after', 2, 4, ' twice', 'A 🦉 twice B'), ('add', 6, 6, '\n ', 'A 🦉 B\n '),
    ('update', 0, 6, '  Complete.\n', '  Complete.\n'),
])
def test_utf16_actions_preserve_exact_unicode_and_whitespace(action, start, end, replacement, expected):
    text = 'A 🦉 B'
    chosen = text.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')
    assert apply_selection(text, TextSelection(start=start, end=end, text=chosen), action, replacement) == expected


@pytest.mark.parametrize('position', [0, 1, 2])
@pytest.mark.parametrize('role', ['user', 'narrator', 'assistant', 'ooc'])
def test_passage_edit_preserves_prefix_suffix_roles_and_original_story(client, story, position, role):
    ids = passages(client, story['branch_id'], role)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    source = passage_target(client, story, ids[position])
    edited = '  The revised words.\n\nKeep the ending whitespace.\n'
    pending = proposal(client, source, edited)
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    receipt = apply(client, pending)
    after = client.get(f"/api/branches/{receipt['result']['branch_id']}").json()
    assert [node['text'] for node in after['messages']] == [edited if index == position else node['text'] for index, node in enumerate(before['messages'])]
    assert [node['id'] for node in after['messages'][:position]] == ids[:position]
    assert all(node['role'] == role for node in after['messages'])
    assert all(node['id'] != ids[index] for index, node in enumerate(after['messages']) if index >= position)
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert receipt['result']['preserved_suffix_count'] == 2 - position
    with client.app.state.database.connect() as connection:
        assert node_state(connection, after['head_id']) == node_state(connection, before['messages'][position]['parent_id'])
    restored = undo(client, receipt)['receipt']
    restored_branch = client.get(f"/api/branches/{restored['result']['branch_id']}").json()
    assert [node['text'] for node in restored_branch['messages']] == [node['text'] for node in before['messages']]


def test_undo_keeps_prose_appended_after_the_edit_and_does_not_replay_models(client, story):
    ids = passages(client, story['branch_id'])
    receipt = apply(client, proposal(client, passage_target(client, story, ids[1]), 'Changed middle.'))
    after = receipt['result']['branch_id']
    append(client, after, 'Independent later prose.', 0)
    restored = undo(client, receipt)['receipt']
    result = client.get(f"/api/branches/{restored['result']['branch_id']}").json()
    assert [item['text'] for item in result['messages']] == ['Unique passage number 0.', 'Unique passage number 1.', 'Unique passage number 2.', 'Independent later prose.']
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM generations').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM mechanic_opportunities').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM text_edit_receipts').fetchone()[0] == 2


def test_empty_replacement_is_an_omission_and_later_restore_keeps_edited_text(client, story):
    ids = passages(client, story['branch_id'])
    edited = apply(client, proposal(client, passage_target(client, story, ids[1]), 'The revised middle.'))
    removed = revise(client, edited['result']['branch_id'], edited['result']['node_id'])
    restored = revise(client, removed['branch_id'], removed['node_id'], 'restore')
    assert client.get(f"/api/branches/{restored['branch_id']}").json()['messages'][1]['text'] == 'The revised middle.'
    omission = apply(client, proposal(client, passage_target(client, story, ids[1]), ''))
    omitted = client.get(f"/api/branches/{omission['result']['branch_id']}").json()
    assert omitted['messages'][1]['metadata']['removed'] and omitted['messages'][1]['text'] == ''
    assert undo(client, omission)['receipt']['after_target']['text'] == 'Unique passage number 1.'


def test_changed_target_requires_explicit_exact_rebase_and_same_destination(client, story):
    ids = passages(client, story['branch_id'])
    before = passage_target(client, story, ids[1])
    pending = proposal(client, before, 'New middle.')
    append(client, story['branch_id'], 'A later independent passage.', 3)
    result = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0, 'acknowledge_state_reset': True})
    assert result.status_code == 409 and 'rebase' in result.text
    current = target(client, before['ref'])
    body = {'operation_id': uuid4().hex, 'target': current['ref'], 'expected_version': current['version'], 'expected_revision': 0,
            'selection': whole_text(current['text']), 'action': 'update', 'replacement': 'New middle.'}
    wrong = {**body, 'target': {**current['ref'], 'node_id': ids[0]}}
    assert client.post(f"/api/text-edits/{pending['id']}/rebase", json=wrong).status_code == 400
    rebased = client.post(f"/api/text-edits/{pending['id']}/rebase", json=body)
    assert rebased.status_code == 201, rebased.text
    receipt = apply(client, rebased.json())
    assert receipt['result']['preserved_suffix_count'] == 2
    assert client.get(f"/api/text-edits/{pending['id']}").json()['status'] == 'dismissed'


def test_dismiss_edit_and_double_application_follow_proposal_revision(client, story):
    source = target(client, {'kind': 'story-brief', 'story_id': story['story_id']})
    pending = proposal(client, source, 'First wording.')
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'replacement': 'Chosen wording.'}
    changed = client.patch(f"/api/text-edits/{pending['id']}", json=body)
    assert changed.status_code == 200 and changed.json()['revision'] == 1
    assert client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0}).status_code == 409
    receipt = apply(client, changed.json())
    assert receipt['replacement'] == 'Chosen wording.'
    assert client.patch(f"/api/text-edits/{pending['id']}", json={**body, 'operation_id': uuid4().hex, 'expected_revision': 1}).status_code == 409
    dismissed = proposal(client, target(client, source['ref']), 'Never applied.')
    for _ in range(2):
        assert client.post(f"/api/text-edits/{dismissed['id']}/dismiss", json={'operation_id': uuid4().hex, 'expected_revision': 0}).status_code == 200
    assert client.post(f"/api/text-edits/{dismissed['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0}).status_code == 409


def test_brief_undo_preserves_other_story_changes_and_conflicts_on_changed_text(client, story):
    source = target(client, {'kind': 'story-brief', 'story_id': story['story_id']})
    receipt = apply(client, proposal(client, source, 'A quiet orchard.'))
    current = client.get(f"/api/stories/{story['story_id']}").json()
    update = {'title': 'A renamed Story', 'premise': current['premise'], 'settings': current['settings'], 'archived': False, 'expected_revision': current['revision']}
    assert client.put(f"/api/stories/{story['story_id']}", json=update).status_code == 200
    assert undo(client, receipt)['status'] == 'applied'
    current = client.get(f"/api/stories/{story['story_id']}").json()
    assert current['title'] == 'A renamed Story' and current['premise'] == ''
    again = apply(client, proposal(client, target(client, source['ref']), 'A different orchard.'))
    newer = apply(client, proposal(client, target(client, source['ref']), 'Independent newer brief.'))
    inverse = undo(client, again)
    assert inverse['status'] == 'conflict' and inverse['proposal']['after_text'] == ''
    assert client.get(f"/api/stories/{story['story_id']}").json()['premise'] == newer['after_target']['text']


@pytest.mark.parametrize('purpose', ['composer', 'author-note', 'scene-goal'])
def test_unsent_document_changes_are_versioned_and_do_not_create_narrative(client, story, purpose):
    source = target(client, {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': purpose})
    current = save_document(client, source, ' Unsent 🦉 text.\n')
    receipt = apply(client, proposal(client, current, ' Revised unsent words.\n'))
    assert target(client, source['ref'])['text'] == ' Revised unsent words.\n'
    newer = save_document(client, target(client, source['ref']), 'Independent draft changes.')
    inverse = undo(client, receipt)
    assert inverse['status'] == 'conflict'
    assert target(client, source['ref']) == newer
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    with Database(client.app.state.database.path).connect() as connection:
        assert read_receipt(connection, receipt['id']) == receipt


def test_target_scope_selection_and_non_text_write_attempts_are_rejected(client, story):
    node = append(client, story['branch_id'], 'A 🦉 B', 0)
    source = passage_target(client, story, node)
    body = {'operation_id': uuid4().hex, 'target': source['ref'], 'expected_version': source['version'],
            'selection': {'start': 2, 'end': 3, 'text': '🦉'}, 'action': 'replace', 'replacement': 'x'}
    assert client.post('/api/text-edits', json=body).status_code == 400
    assert client.post('/api/text-edits', json={**body, 'selection': {'start': 2, 'end': 4, 'text': 'wrong'}}).status_code == 409
    assert client.post('/api/text-edits', json={**body, 'origin': {'kind': 'companion', 'authorized': True}}).status_code == 422
    assert client.post('/api/text-edits', content=json.dumps({**body, 'replacement': '\ud800'}), headers={'Content-Type': 'application/json'}).status_code == 422
    foreign = client.post('/api/stories', json={'title': 'Other'}).json()
    assert client.post('/api/text-targets/read', json={'target': {**source['ref'], 'story_id': foreign['story_id']}}).status_code == 409
    assert client.post('/api/text-targets/read', json={'target': {'kind': 'settings', 'story_id': story['story_id']}}).status_code == 422


def test_edit_archive_twice_keeps_prose_receipts_and_book_sources(client, story):
    document, _ = book_fixture(client, story)
    source_node = document['chapters'][0]['scenes'][0]['from_node_id']
    source = passage_target(client, story, source_node)
    receipt = apply(client, proposal(client, source, 'Revised opening.'))
    preview = client.get(f"/api/stories/{story['story_id']}/manuscript/preview").json()
    assert 'Revised opening.' not in json.dumps(preview)
    file, archived = backup(client, story)
    assert len(archived['data']['text_edit_receipts']) == 1
    _, mapping = restore(client, file)
    imported = client.get(f"/api/text-edit-receipts/{mapping[receipt['id']]}").json()
    assert imported['before_target']['text'] == source['text'] and imported['after_target']['text'] == 'Revised opening.'
    assert imported['result']['source_head_id'] == mapping[receipt['result']['source_head_id']]
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    _, again = restore(client, second)
    repeat = client.get(f"/api/text-edit-receipts/{again[mapping[receipt['id']]]}").json()
    assert repeat['before_target']['text'] == source['text']
    assert undo(client, repeat)['status'] == 'applied'


def test_archive_rejects_forged_edit_receipts_and_missing_suffix(client, story):
    ids = passages(client, story['branch_id'])
    receipt = apply(client, proposal(client, passage_target(client, story, ids[1]), 'Changed.'))
    append(client, receipt['result']['branch_id'], 'Independent later prose.', 0)
    _, document = backup(client, story)
    bad = deepcopy(document)
    bad['data']['text_edit_receipts'][0]['replacement'] = 'Unreviewed'
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400
    bad = deepcopy(document)
    target_row = next(item for item in bad['data']['branches'] if item['id'] == receipt['result']['branch_id'])
    target_row['head_id'] = receipt['result']['node_id']
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400
    bad = deepcopy(document)
    after = json.loads(bad['data']['text_edit_receipts'][0]['after_target'])
    after['basis']['revision'] = 1
    after['version'] = snapshot_version(after)
    bad['data']['text_edit_receipts'][0]['after_target'] = json.dumps(after)
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400


def test_v41_upgrade_keeps_existing_groups_strict(client, story):
    _, document = backup(client, story)
    document['version'] = 41
    document['data'] = {key: document['data'][key] for key in V41_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 201
    document['data']['text_documents'] = []
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


def test_history_loads_summaries_and_opens_full_edits_by_identity(client, story):
    node = append(client, story['branch_id'], 'Long prose. ' * 5000, 0)
    pending = proposal(client, passage_target(client, story, node), 'Revised prose.')
    receipt = apply(client, pending)
    response = client.get(f"/api/stories/{story['story_id']}/text-edits")
    assert response.status_code == 200 and len(response.content) < 1000
    assert response.json() == [{'id': pending['id'], 'label': pending['target']['label'], 'status': 'applied',
                                'created_at': pending['created_at'], 'receipt_id': receipt['id']}]
    assert client.get(f"/api/text-edits/{pending['id']}").json()['receipt'] == receipt


@pytest.mark.parametrize('kind', ['story-brief', 'composer', 'author-note', 'scene-goal'])
@pytest.mark.parametrize('replacement', ['', ' Revised 🦉 wording.\n'])
def test_field_edit_restore_preserves_identity_revision_and_conflicting_undo(client, story, kind, replacement):
    ref = {'kind': 'story-brief', 'story_id': story['story_id']}
    if kind != 'story-brief':
        ref = {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': kind}
    first = apply(client, proposal(client, target(client, ref), replacement))
    second = apply(client, proposal(client, target(client, ref), replacement))
    changed = apply(client, proposal(client, target(client, ref), 'Newer words.'))
    inverse = undo(client, second)
    assert inverse['status'] == 'conflict'
    current = target(client, ref)
    rebased = client.post(f"/api/text-edits/{inverse['proposal']['id']}/rebase", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'target': ref, 'expected_version': current['version'],
        'selection': whole_text(current['text']), 'action': 'update', 'replacement': 'Newer words, revised explicitly.',
    })
    assert rebased.status_code == 201, rebased.text
    last = apply(client, rebased.json())
    file, archived = backup(client, story)
    _, mapping = restore(client, file)
    for receipt in (first, second, changed, last):
        restored = client.get(f"/api/text-edit-receipts/{mapping[receipt['id']]}").json()
        assert restored['before_target']['text'] == receipt['before_target']['text']
        assert restored['after_target']['text'] == receipt['after_target']['text']
        assert restored['result'] == {key: mapping[value] for key, value in receipt['result'].items()}
    forged = deepcopy(archived)
    forged['data']['text_edit_receipts'][0]['result'] = json.dumps({'story_id': 'wrong-destination'})
    assert client.post('/api/archives/imports', json={'content': json.dumps(forged)}).status_code == 400


def test_text_edit_uses_prefix_chance_state_without_replaying_rolls(client, story):
    from tests.test_mechanics import accept_manual, configure, prepare
    configure(client, story)
    ids = []
    for index in range(3):
        opportunity = prepare(client, story['branch_id'], revision=index)
        ids.append(accept_manual(client, story['branch_id'], opportunity['id'], revision=index)['node_id'])
    pending = proposal(client, passage_target(client, story, ids[1]), 'A different outcome, with later prose preserved.')
    blocked = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0})
    assert blocked.status_code == 409
    receipt = apply(client, pending)
    revised = client.get(f"/api/branches/{receipt['result']['branch_id']}").json()
    assert revised['mechanics']['state']['beat'] == 1 and revised['mechanics']['pending'] is None
    assert client.get(f"/api/branches/{story['branch_id']}").json()['mechanics']['state']['beat'] == 3
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM mechanic_opportunities').fetchone()[0] == 3


def test_text_edit_excludes_derived_memory_after_revision_boundary(client):
    from server.memory.summary_versions import applicable_versions
    from tests.test_memory_controls import entry, evidence, save, view
    from tests.test_plan_edits import save as save_plan
    from tests.test_plan_edits import view as plan_view
    from tests.test_story_summaries import publication, setup, started
    story, _ = setup(client)
    branch = story['branch_id']
    root = client.get(f'/api/branches/{branch}').json()['head_id']
    run = started(client, branch)
    assert client.post(f"/api/summaries/{run['id']}/versions", json=publication(client, run, branch)).status_code == 201
    save(client, branch, [entry(evidence(client, branch))])
    save_plan(client, branch)
    revision = client.get(f'/api/branches/{branch}').json()['revision']
    append(client, branch, 'Keep this later prose pending review.', revision)
    prior_controls, prior_plans = view(client, branch), plan_view(client, branch)
    receipt = apply(client, proposal(client, passage_target(client, story, root), 'The opening changed.'))
    after = receipt['result']['branch_id']
    assert view(client, after)['entries'] == [] and plan_view(client, after)['entries'] == []
    assert view(client, branch) == prior_controls and plan_view(client, branch) == prior_plans
    with client.app.state.database.connect() as connection:
        row = dict(connection.execute('SELECT * FROM branches WHERE id=?', (after,)).fetchone())
        assert applicable_versions(connection, row) == {}
