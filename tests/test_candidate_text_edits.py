import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import V43_TABLES
from server.database import decode
from server.generation_models import AcceptCandidate
from server.phrases.detection import digest
from tests.test_archives import backup, restore
from tests.test_cleanup import ORIGINAL, select, setup, start, wait_cleanup
from tests.test_generations import finished
from tests.test_history import append
from tests.test_reading_time_cleanup import reading_setup, settled
from tests.test_text_edits import apply, proposal, target, undo


def fixture(client, story, cleanup=False, mode='valid'):
    provider = setup(client, story, enabled=cleanup, mode=mode)
    run, _ = start(client, story)
    detail = finished(client, run['id'])
    candidate = detail['candidates'][0]
    ref = {'kind': 'candidate', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'candidate_id': candidate['id']}
    return provider, detail, candidate, target(client, ref)


def current(client, run_id):
    return client.get(f'/api/generations/{run_id}').json()['candidates'][0]


def accept(client, candidate, **kwargs):
    body = {'operation_id': uuid4().hex, 'expected_wording_version': candidate['wording_version'], **kwargs}
    return client.post(f"/api/candidates/{candidate['id']}/accept", json=body)


def test_author_revision_preserves_provider_output_and_requires_explicit_exact_acceptance(client, story):
    provider, run, candidate, source = fixture(client, story)
    receipt = apply(client, proposal(client, source, '  Author revision 🦉.\n'))
    updated = current(client, run['id'])
    assert updated['output'] == ORIGINAL
    assert updated['text_edit']['text'] == receipt['after_target']['text']
    assert updated['wording_version'] == receipt['after_target']['version']
    assert updated['usage'] == candidate['usage'] and len(provider.calls) == 1
    assert client.get(f"/api/generations/{run['id']}").json()['snapshot'] == run['snapshot']
    assert not client.get(f"/api/branches/{story['branch_id']}").json()['messages']
    assert accept(client, candidate).status_code == 409
    assert client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex}).status_code == 409
    body = {'operation_id': uuid4().hex, 'expected_wording_version': updated['wording_version']}
    result = client.post(f"/api/candidates/{candidate['id']}/accept", json=body)
    assert result.status_code == 200, result.text
    assert client.post(f"/api/candidates/{candidate['id']}/accept", json=body).json() == result.json()
    node = client.get(f"/api/branches/{story['branch_id']}").json()['messages'][0]
    assert node['text'] == receipt['after_target']['text']
    assert node['metadata']['edit_receipt_id'] == receipt['id']
    assert current(client, run['id'])['output'] == ORIGINAL
    assert client.post(f"/api/text-edit-receipts/{receipt['id']}/undo", json={'operation_id': uuid4().hex}).status_code == 409
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == [node]


def test_draft_undo_and_conflicting_inverse_preserve_independent_author_revisions(client, story):
    _, run, _, source = fixture(client, story)
    first = apply(client, proposal(client, source, 'First revision.'))
    second = apply(client, proposal(client, target(client, source['ref']), 'Independent second revision.'))
    conflict = undo(client, first)
    assert conflict['status'] == 'conflict'
    assert current(client, run['id'])['text_edit']['text'] == 'Independent second revision.'
    restored = undo(client, second)['receipt']
    assert restored['after_target']['text'] == 'First revision.'
    assert restored['after_target']['basis']['revision'] == 3
    assert undo(client, restored)['receipt']['after_target']['text'] == 'Independent second revision.'


def test_cleanup_source_and_original_provider_text_remain_distinct_from_author_revision(client, story):
    provider, run, candidate, source = fixture(client, story, cleanup=True)
    assert source['text'] == candidate['cleanup']['cleaned']
    assert source['basis']['cleanup_id'] == candidate['cleanup']['id']
    receipt = apply(client, proposal(client, source, 'Chosen author wording.'))
    assert select(client, current(client, run['id']), 'original').status_code == 409
    assert current(client, run['id'])['cleanup'] == candidate['cleanup']
    restored = undo(client, receipt)['receipt']
    assert restored['after_target']['text'] == candidate['cleanup']['cleaned']
    original = apply(client, proposal(client, target(client, source['ref']), ORIGINAL))
    assert original['after_target']['text'] == ORIGINAL
    assert current(client, run['id'])['cleanup']['cleaned'] == candidate['cleanup']['cleaned']
    assert len(provider.calls) == 2


def test_cleanup_selection_change_invalidates_a_pending_draft_edit_and_keep_version(client, story):
    _, run, candidate, source = fixture(client, story, cleanup=True)
    pending = proposal(client, source, 'Based on the cleaned draft.')
    assert select(client, candidate, 'original').status_code == 200
    result = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': 0})
    assert result.status_code == 409
    assert accept(client, candidate).status_code == 409
    assert current(client, run['id'])['text_edit'] is None


def test_late_reading_cleanup_cannot_replace_an_explicit_author_revision(client, story):
    provider = reading_setup(client, story)
    run, _ = start(client, story)
    candidate = wait_cleanup(client, run)
    assert candidate['status'] == 'done'
    ref = {'kind': 'candidate', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'candidate_id': candidate['id']}
    receipt = apply(client, proposal(client, target(client, ref), 'Author words before cleanup completes.'))
    provider.release = True
    updated = settled(client, run)
    assert updated['cleanup']['status'] == 'done'
    assert updated['text_edit']['text'] == receipt['after_target']['text']
    assert updated['wording_version'] == receipt['after_target']['version']
    assert accept(client, updated).status_code == 200
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][0]['text'] == receipt['after_target']['text']


@pytest.mark.parametrize('status', ['running', 'cleaning', 'queued', 'cancelled', 'error', 'interrupted'])
def test_partial_or_unfinished_output_never_becomes_an_author_edit_target(client, story, status):
    _, _, candidate, source = fixture(client, story)
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('UPDATE candidates SET status=? WHERE id=?', (status, candidate['id']))
    assert client.post('/api/text-targets/read', json={'target': source['ref']}).status_code == 409
    body = {'operation_id': uuid4().hex, 'target': source['ref'], 'expected_version': source['version'], 'selection': {'start': 0, 'end': 0, 'text': ''}, 'action': 'insert-before', 'replacement': 'Added'}
    assert client.post('/api/text-edits', json=body).status_code == 409


def test_draft_target_cannot_switch_story_or_branch(client, story):
    _, _, _, source = fixture(client, story)
    other = client.post('/api/stories', json={'title': 'Other Story'}).json()
    for changed in ({'story_id': other['story_id']}, {'branch_id': other['branch_id']}):
        response = client.post('/api/text-targets/read', json={'target': {**source['ref'], **changed}})
        assert response.status_code == 409


def test_edited_stale_draft_uses_original_starting_point_without_replaying_model_calls(client, story):
    provider, run, _, source = fixture(client, story)
    apply(client, proposal(client, source, 'Another possible beginning.'))
    append(client, story['branch_id'], 'Independent accepted history.', 0)
    edited = current(client, run['id'])
    assert accept(client, edited).status_code == 409
    result = accept(client, edited, as_new_branch=True)
    assert result.status_code == 200, result.text
    assert result.json()['branch_id'] != story['branch_id']
    assert client.get(f"/api/branches/{result.json()['branch_id']}").json()['messages'][0]['text'] == 'Another possible beginning.'
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][0]['text'] == 'Independent accepted history.'
    assert len(provider.calls) == 1


def test_empty_author_revision_stays_a_draft_and_cannot_be_kept(client, story):
    _, run, _, source = fixture(client, story)
    receipt = apply(client, proposal(client, source, ''))
    assert accept(client, current(client, run['id'])).status_code == 409
    assert undo(client, receipt)['receipt']['after_target']['text'] == ORIGINAL


def test_alternate_keeps_original_provider_inputs_and_never_inherits_an_author_overlay(client, story):
    provider, run, candidate, source = fixture(client, story)
    apply(client, proposal(client, source, 'Author revision.'))
    alternate = client.post(f"/api/candidates/{candidate['id']}/alternatives", json={'operation_id': uuid4().hex})
    assert alternate.status_code == 201, alternate.text
    result = finished(client, run['id'])
    next_candidate = next(row for row in result['candidates'] if row['id'] == alternate.json()['candidate_id'])
    assert next_candidate['output'] == ORIGINAL and next_candidate['text_edit'] is None
    assert provider.calls[0] == provider.calls[1]


def test_accepted_and_unaccepted_author_edits_survive_repeated_archive_restore(client, story):
    _, run, _, source = fixture(client, story, cleanup=True)
    first = apply(client, proposal(client, source, 'Unaccepted revision.'))
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    restored = current(client, mapping[run['id']])
    assert restored['output'] == ORIGINAL and restored['text_edit']['text'] == 'Unaccepted revision.'
    assert undo(client, {**first, 'id': mapping[first['id']]})['status'] == 'applied'
    assert accept(client, current(client, mapping[run['id']])).status_code == 200
    second, restored_document = backup(client, copied)
    _, next_map = restore(client, second)
    again = current(client, next_map[mapping[run['id']]])
    assert again['output'] == ORIGINAL and again['accepted_node_id']
    assert client.get(f"/api/branches/{again['accepted_branch_id']}").json()['messages'][0]['text'] == again['text_edit']['text']
    before_inputs = decode(document['data']['generations'][0]['snapshot'])['content']
    after_inputs = decode(restored_document['data']['generations'][0]['snapshot'])['content']
    assert before_inputs == after_inputs
    assert decode(document['data']['candidate_cleanups'][0]['snapshot'])['content'] == decode(restored_document['data']['candidate_cleanups'][0]['snapshot'])['content']
    assert all(row['output'] == ORIGINAL for row in restored_document['data']['generation_attempts'])


@pytest.mark.parametrize('damage', ['text', 'source', 'head', 'receipt'])
def test_archive_rejects_inconsistent_author_revision_provenance(client, story, damage):
    _, _, _, source = fixture(client, story)
    apply(client, proposal(client, source, 'Author revision.'))
    _, document = backup(client, story)
    bad = deepcopy(document)
    if damage == 'text':
        bad['data']['candidate_text_heads'][0]['text'] = 'Changed without a receipt.'
    elif damage == 'source':
        bad['data']['candidates'][0]['output'] = 'Changed provider text.'
    elif damage == 'head':
        bad['data']['candidate_text_heads'][0]['revision'] += 1
    else:
        saved = decode(bad['data']['text_edit_receipts'][0]['result'])
        saved['attempt'] += 1
        bad['data']['text_edit_receipts'][0]['result'] = json.dumps(saved)
    result = client.post('/api/archives/imports', json={'content': json.dumps(bad)})
    assert result.status_code == 400, result.text


def test_v43_upgrade_requires_original_groups_and_preserves_plain_drafts(client, story):
    fixture(client, story)
    _, document = backup(client, story)
    document['version'] = 43
    document['data'] = {key: document['data'][key] for key in V43_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 201
    document['data']['candidate_text_heads'] = []
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


def test_old_acceptance_payloads_keep_their_original_operation_shape():
    assert 'expected_wording_version' not in AcceptCandidate(operation_id=uuid4().hex).model_dump()


def test_continuity_revision_uses_exact_selected_author_text_and_freezes_that_edition(client, story):
    from tests.test_continuity_revision import original, revise, revision_body
    run, candidate, provider = original(client, story)
    ref = {'kind': 'candidate', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'candidate_id': candidate['id']}
    applied = apply(client, proposal(client, target(client, ref), '  The author’s chosen starting draft.\n'))
    edited = current(client, run['id'])
    body = revision_body(edited, original_sha256=digest(edited['text_edit']['text']), expected_wording_version=edited['wording_version'])
    response = revise(client, edited, body)
    assert response.status_code == 201, response.text
    result = finished(client, run['id'])
    revised = next(row for row in result['candidates'] if row['id'] == response.json()['candidate_id'])
    frozen = revised['usage']['continuity_revision']
    assert frozen['version'] == 3 and frozen['source_edit_receipt_id'] == applied['id']
    assert decode(frozen['content'])['draft'] == applied['after_target']['text']
    assert decode(frozen['content'])['context'] == decode(result['snapshot']['content'])
    assert provider.calls[-1][1:] == (frozen['prompt'], frozen['content'])
    apply(client, proposal(client, target(client, ref), 'Later independent author changes.'))
    assert revise(client, edited, body).json() == response.json()
    assert revise(client, edited, {**body, 'operation_id': uuid4().hex}).status_code == 409
    assert len(provider.calls) == 2
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    receipt = next(row for row in restored['candidates'] if row['id'] == mapping[revised['id']])['usage']['continuity_revision']
    assert receipt['content'] == frozen['content']
    assert receipt['source_edit_receipt_id'] == mapping[applied['id']]
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    second, _ = backup(client, copied)
    restore(client, second)
