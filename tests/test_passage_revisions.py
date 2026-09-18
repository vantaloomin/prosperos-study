from uuid import uuid4

import pytest

from server.branches import path_nodes
from server.database import decode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.memory.prose_sources import source_chunks
from server.side_context import branch_sources
from tests.test_archives import backup, restore
from tests.test_mechanics import accept_manual, configure, prepare
from tests.test_profiles import make_profile


def passages(client, branch, role='narrator'):
    ids = []
    for index in range(3):
        response = client.post(f'/api/branches/{branch}/messages', json={
            'operation_id': uuid4().hex, 'expected_revision': index,
            'role': role, 'text': f'Unique passage number {index}.'})
        assert response.status_code == 201
        ids.append(response.json()['node_id'])
    return ids


def revise(client, branch, node, action='remove', **extra):
    current = client.get(f'/api/branches/{branch}').json()
    body = {'operation_id': uuid4().hex, 'expected_revision': current['revision'], 'node_id': node,
            'action': action, 'name': 'Revised path', 'acknowledge_state_reset': True, **extra}
    response = client.post(f'/api/branches/{branch}/passage-revisions', json=body)
    assert response.status_code == 201, response.text
    assert client.post(f'/api/branches/{branch}/passage-revisions', json=body).json() == response.json()
    return response.json()


@pytest.mark.parametrize('position', [0, 1, 2])
@pytest.mark.parametrize('role', ['user', 'narrator', 'assistant', 'ooc'])
def test_remove_restore_preserves_roles_siblings_and_suffix(client, story, position, role):
    branch = story['branch_id']
    ids = passages(client, branch, role)
    original = client.get(f'/api/branches/{branch}').json()
    revision = revise(client, branch, ids[position])
    revised = client.get(f"/api/branches/{revision['branch_id']}").json()
    assert [node['text'] for node in revised['messages']] == [
        '' if index == position else f'Unique passage number {index}.' for index in range(3)]
    assert revised['messages'][position]['metadata']['removed']
    assert all(node['role'] == role for node in revised['messages'])
    assert client.get(f'/api/branches/{branch}').json() == original
    undone = revise(client, revision['branch_id'], revision['node_id'], 'restore')
    restored = client.get(f"/api/branches/{undone['branch_id']}").json()
    assert [node['text'] for node in restored['messages']] == [node['text'] for node in original['messages']]
    assert client.get(f"/api/branches/{revision['branch_id']}").json() == revised


def test_removed_text_excluded_from_all_current_content_and_inherited_by_forks(client, story):
    branch = story['branch_id']
    ids = passages(client, branch)
    make_profile(client, 'Writer', primary=True)
    revised = revise(client, branch, ids[1])
    new_branch = client.get(f"/api/branches/{revised['branch_id']}").json()
    fork = client.post(f"/api/branches/{new_branch['id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'node_id': new_branch['head_id'], 'name': 'Child'}).json()
    omitted = 'Unique passage number 1.'
    for target in [new_branch['id'], fork['branch_id']]:
        with client.app.state.database.connect() as connection:
            row = one(connection, 'SELECT * FROM branches WHERE id=?', (target,))
            assert len(path_nodes(connection, row['head_id'])) == 2
            assert omitted not in str(source_chunks(connection, row['head_id']))
            assert omitted not in str(branch_sources(connection, row))
            snapshot, _ = generation_snapshot(connection, target, GenerateRequest(operation_id=uuid4().hex, expected_revision=0))
            assert omitted not in snapshot['content']
            assert 'Passage removed' not in snapshot['content']
        exported = client.post(f'/api/branches/{target}/transcript', json={'expected_revision': 0}).json()
        assert omitted not in exported['content'] and exported['message_count'] == 2
    file, document = backup(client, story)
    assert omitted in str(document)  # Private archive preserves the original path.
    _, mapping = restore(client, file)
    restored = client.get(f"/api/branches/{mapping[new_branch['id']]}").json()
    marker = restored['messages'][1]
    assert marker['metadata']['original_node_id'] == mapping[ids[1]]
    undone = revise(client, restored['id'], marker['id'], 'restore')
    assert client.get(f"/api/branches/{undone['branch_id']}").json()['messages'][1]['text'] == omitted


def test_revision_requires_acknowledgement_and_current_path_membership(client, story):
    branch = story['branch_id']
    ids = passages(client, branch)
    body = {'operation_id': uuid4().hex, 'expected_revision': 2, 'node_id': ids[1],
            'action': 'remove', 'name': 'New path', 'acknowledge_state_reset': True}
    endpoint = f'/api/branches/{branch}/passage-revisions'
    assert client.post(endpoint, json=body).status_code == 409
    assert client.post(endpoint, json={**body, 'expected_revision': 3, 'acknowledge_state_reset': False}).status_code == 422
    assert client.post(endpoint, json={**body, 'expected_revision': 3, 'node_id': 'missing'}).status_code == 409
    assert client.post(endpoint, json={**body, 'expected_revision': 3, 'action': 'restore'}).status_code == 409


def test_revision_discards_later_mechanics_without_replaying_rolls(client, story):
    branch = story['branch_id']
    configure(client, story)
    ids = []
    for index in range(3):
        opportunity = prepare(client, branch, revision=index)
        ids.append(accept_manual(client, branch, opportunity['id'], revision=index)['node_id'])
    before = client.get(f'/api/branches/{branch}').json()['mechanics']['state']
    revised = revise(client, branch, ids[1])
    detail = client.get(f"/api/branches/{revised['branch_id']}").json()
    assert detail['mechanics']['state']['beat'] == 1
    assert detail['mechanics']['pending'] is None
    with client.app.state.database.connect() as connection:
        original = decode(one(connection, 'SELECT state FROM node_mechanics WHERE node_id=?', (ids[2],))['state'])
        assert original == before and original['beat'] == 3
        assert one(connection, 'SELECT count(*) AS count FROM mechanic_opportunities')['count'] == 3


def test_removed_generated_passage_keeps_its_historical_receipt(client, story):
    from tests.test_generations import DraftProvider, finished, generate
    from tests.test_history import append
    client.app.state.runner.provider = DraftProvider()
    make_profile(client, 'Writer', primary=True)
    append(client, story['branch_id'], 'Before the draft.', 0)
    run = generate(client, story, revision=1)
    candidate = finished(client, run['id'])['candidates'][0]
    accepted = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex}).json()
    append(client, story['branch_id'], 'After the draft.', 2)
    before = client.get(f"/api/generations/{run['id']}").json()
    revised = revise(client, story['branch_id'], accepted['node_id'])
    assert client.get(f"/api/generations/{run['id']}").json() == before
    current = client.get(f"/api/branches/{revised['branch_id']}").json()
    assert [node['text'] for node in current['messages']] == ['Before the draft.', '', 'After the draft.']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['snapshot']['content'] == before['snapshot']['content']


def test_removal_excludes_dependent_summaries_plans_and_character_evidence(client):
    from server.memory.summary_versions import applicable_versions
    from tests.test_history import append
    from tests.test_memory_controls import entry, evidence, save, view
    from tests.test_plan_edits import save as save_plan
    from tests.test_plan_edits import view as plan_view
    from tests.test_story_summaries import TEXT, publication, setup, started
    story, _ = setup(client)
    branch = story['branch_id']
    root = client.get(f'/api/branches/{branch}').json()['head_id']
    run = started(client, branch)
    published = client.post(f"/api/summaries/{run['id']}/versions", json=publication(client, run, branch))
    assert published.status_code == 201
    save(client, branch, [entry(evidence(client, branch))])
    save_plan(client, branch)
    revision = client.get(f'/api/branches/{branch}').json()['revision']
    append(client, branch, 'Later prose remains authored, pending review.', revision)
    original_controls, original_plans = view(client, branch), plan_view(client, branch)
    revised = revise(client, branch, root)
    assert view(client, revised['branch_id'])['entries'] == []
    assert plan_view(client, revised['branch_id'])['entries'] == []
    assert view(client, branch) == original_controls and plan_view(client, branch) == original_plans
    with client.app.state.database.connect() as connection:
        row = one(connection, 'SELECT * FROM branches WHERE id=?', (revised['branch_id'],))
        assert applicable_versions(connection, row) == {}
        snapshot, _ = generation_snapshot(connection, row['id'], GenerateRequest(operation_id=uuid4().hex, expected_revision=0))
        assert TEXT not in snapshot['content']
        assert 'Elin has not tested' not in snapshot['content']
        assert 'Elin makes an untested claim' not in snapshot['content']
        assert TEXT not in str(branch_sources(connection, row))
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert view(client, mapping[revised['branch_id']])['entries'] == []
