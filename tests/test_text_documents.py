from uuid import uuid4

import pytest

from server.models import MessageCreate
from server.operations import remember
from server.scenes.models import SceneCreate
from server.text_edits.models import TextTarget
from server.text_edits.targets import save_document as write_document
from tests.test_archives import backup, restore
from tests.test_text_edits import apply, proposal, save_document, target, undo


def draft(client, story, purpose='composer', text='  Unsent 🦉 words.\n'):
    ref = {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': purpose}
    return save_document(client, target(client, ref), text)


def message(source, role='narrator', revision=0):
    return {'operation_id': uuid4().hex, 'expected_revision': revision, 'role': role,
            'text': source['text'], 'expected_document_version': source['version']}


@pytest.mark.parametrize('purpose,role', [('composer', 'narrator'), ('composer', 'user'), ('author-note', 'ooc')])
def test_acceptance_consumes_only_the_exact_draft_and_preserves_whitespace(client, story, purpose, role):
    source = draft(client, story, purpose)
    unrelated = draft(client, story, 'scene-goal', 'Next scene goal.')
    body = message(source, role)
    path = f"/api/branches/{story['branch_id']}/messages"
    result = client.post(path, json=body)
    assert result.status_code == 201, result.text
    assert client.post(path, json=body).json() == result.json()
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['messages'][-1]['text'] == source['text']
    assert branch['messages'][-1]['role'] == role
    assert target(client, source['ref'])['text'] == ''
    assert target(client, unrelated['ref']) == unrelated
    later = save_document(client, target(client, source['ref']), 'Independent later words.')
    assert client.post(path, json=body).json() == result.json()
    assert target(client, source['ref']) == later
    assert client.post(path, json={**body, 'operation_id': uuid4().hex, 'expected_revision': 1}).status_code == 409
    assert target(client, source['ref']) == later


def test_changed_unsent_text_or_wrong_role_cannot_be_accepted(client, story):
    source = draft(client, story)
    path = f"/api/branches/{story['branch_id']}/messages"
    assert client.post(path, json=message(source, 'ooc')).status_code == 409
    wrong = {**message(source), 'text': 'Different wording'}
    assert client.post(path, json=wrong).status_code == 409
    current = save_document(client, source, 'Changed in another window.')
    assert client.post(path, json=message(source)).status_code == 409
    assert target(client, source['ref']) == current
    assert not client.get(f"/api/branches/{story['branch_id']}").json()['messages']


def test_a_failed_acceptance_keeps_the_saved_draft(client, story):
    source = draft(client, story)
    result = client.post(f"/api/branches/{story['branch_id']}/messages", json={**message(source), 'opportunity_id': 'missing-beat'})
    assert result.status_code in {404, 409}, result.text
    assert target(client, source['ref']) == source


def test_scoped_edit_of_unsent_text_stays_unaccepted_and_undo_after_send_requires_review(client, story):
    source = draft(client, story)
    receipt = apply(client, proposal(client, source, '  Revised but still unsent.\n'))
    current = target(client, source['ref'])
    assert not client.get(f"/api/branches/{story['branch_id']}").json()['messages']
    assert client.post(f"/api/branches/{story['branch_id']}/messages", json=message(current)).status_code == 201
    inverse = undo(client, receipt)
    assert inverse['status'] == 'conflict'
    assert target(client, source['ref'])['text'] == ''
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['messages'][-1]['text'] == current['text']


def test_scene_goal_is_consumed_atomically_and_saved_plan_keeps_its_exact_copy(client, story):
    source = draft(client, story, 'scene-goal', '  A quiet scene.\n')
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'title': 'Quiet', 'direction': source['text'], 'expected_document_version': source['version']}
    path = f"/api/branches/{story['branch_id']}/scenes"
    result = client.post(path, json=body)
    assert result.status_code == 201, result.text
    assert target(client, source['ref'])['text'] == ''
    current = save_document(client, target(client, source['ref']), 'A second plan.')
    assert client.post(path, json=body).json() == result.json()
    assert target(client, source['ref']) == current
    assert client.post(path, json={**body, 'operation_id': uuid4().hex}).status_code == 409
    plan = client.get(f"/api/scenes/{result.json()['id']}").json()
    assert plan['snapshot']['direction'] == source['text']
    assert not client.get(f"/api/branches/{story['branch_id']}").json()['messages']


def test_changed_scene_goal_does_not_create_a_plan(client, story):
    source = draft(client, story, 'scene-goal', 'Initial goal.')
    current = save_document(client, source, 'Revised goal.')
    path = f"/api/branches/{story['branch_id']}/scenes"
    result = client.post(path, json={'operation_id': uuid4().hex, 'expected_revision': 0, 'title': 'Quiet', 'direction': source['text'], 'expected_document_version': source['version']})
    assert result.status_code == 409
    assert not client.get(path).json()
    assert target(client, source['ref']) == current


def test_legacy_operation_payloads_omit_absent_document_versions():
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'text': 'Legacy'}
    assert 'expected_document_version' not in MessageCreate(**body).model_dump()
    scene = SceneCreate(operation_id=uuid4().hex, expected_revision=0, title='Old plan', direction='Old goal')
    assert 'expected_document_version' not in scene.model_dump()


def test_consumed_draft_receipts_and_remaining_unsent_fields_survive_repeated_restore(client, story):
    source = draft(client, story)
    receipt = apply(client, proposal(client, source, '  Accepted exact draft.\n'))
    assert client.post(f"/api/branches/{story['branch_id']}/messages", json=message(target(client, source['ref']))).status_code == 201
    note = draft(client, story, 'author-note', 'Unsent direction.')
    goal = draft(client, story, 'scene-goal', '  A frozen scene goal.\n')
    created = client.post(f"/api/branches/{story['branch_id']}/scenes", json={
        'operation_id': uuid4().hex, 'expected_revision': 1, 'title': 'Future scene', 'direction': goal['text'], 'expected_document_version': goal['version']})
    assert created.status_code == 201, created.text
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    assert target(client, {**source['ref'], **copied})['text'] == ''
    assert target(client, {**note['ref'], **copied})['text'] == note['text']
    assert client.get(f"/api/scenes/{mapping[created.json()['id']]}").json()['snapshot']['direction'] == goal['text']
    assert client.get(f"/api/text-edit-receipts/{mapping[receipt['id']]}").json()['after_target']['text'] == receipt['after_target']['text']
    second, _ = backup(client, copied)
    _, second_map = restore(client, second)
    assert target(client, {**note['ref'], 'story_id': second_map[copied['story_id']], 'branch_id': second_map[copied['branch_id']]})['text'] == note['text']


def test_autosave_checks_versions_without_retaining_a_full_receipt_per_typing_pause(client, story):
    ref = {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': 'composer'}
    source = target(client, ref)
    for number in range(25):
        body = {'target': ref, 'expected_version': source['version'], 'text': f'  Draft number {number}.\n'}
        result = client.put('/api/text-documents/autosave', json=body)
        assert result.status_code == 200, result.text
        assert client.put('/api/text-documents/autosave', json=body).status_code == 409
        source = result.json()
    same = client.put('/api/text-documents/autosave', json={**body, 'expected_version': source['version']})
    assert same.json() == source
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM text_documents').fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM operations WHERE kind='text-document-save'").fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM text_edit_receipts').fetchone()[0] == 0
    wrong = target(client, {'kind': 'story-brief', 'story_id': story['story_id']})
    assert client.put('/api/text-documents/autosave', json={'target': wrong['ref'], 'expected_version': wrong['version'], 'text': 'Never a brief change.'}).status_code == 400
    assert target(client, wrong['ref']) == wrong


def test_previous_document_save_fingerprints_still_recover_after_independent_typing(client, story):
    ref = TextTarget(kind='document', story_id=story['story_id'], branch_id=story['branch_id'], purpose='composer')
    source = target(client, ref.model_dump(exclude_none=True))
    body = {'target': ref.model_dump(), 'operation_id': uuid4().hex, 'expected_version': source['version'], 'text': 'Earlier saved words.'}
    with client.app.state.database.connect(write=True) as connection:
        original = write_document(connection, ref, body['text'])
        # Exact pre-autosave serialized order, rather than the current model dump.
        payload = {'id': None, 'target': body['target'], 'operation_id': body['operation_id'], 'expected_version': body['expected_version'], 'text': body['text']}
        remember(connection, body['operation_id'], 'text-document-save', payload, original)
        later = write_document(connection, ref, 'Independent later typing.')
    response = client.put('/api/text-documents', json=body)
    assert response.status_code == 200, response.text
    assert response.json() == original
    assert target(client, ref.model_dump(exclude_none=True)) == later
