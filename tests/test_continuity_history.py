from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.side_context import branch_sources
from server.workflow.catalog import ROLE_MAP
from server.workflow.context import scoped_sources
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile
from tests.test_scene_continuity import acceptance_body, continuity, ready_continuity
from tests.test_scene_patches import selected_stage
from tests.test_scenes import choose, get_plan, run_stage


def accept(client, run_id, **extra):
    response = client.post(f'/api/scenes/{run_id}/accept', json=acceptance_body(client, run_id, **extra))
    assert response.status_code == 200, response.text
    return response.json()['state']['accepted']


def test_updates_and_thread_resolution_follow_the_selected_history_after_restore(client, story):
    first, _ = ready_continuity(client, story)
    receipt = accept(client, first, selected_ids=['c1', 'c2'])
    original = continuity(client, story['branch_id'])
    second, provider = ready_continuity(client, story)
    assert get_plan(client, second)['snapshot']['continuity'] == original

    def update(result):
        result['changes'][0].update(action='replace', target_id=original['entries'][0]['id'], text='The letter remains sealed.')
        result['changes'][1].update(action='resolve', target_id=original['entries'][1]['id'], text='Fixture director accepts the thread as resolved.')

    provider.corrupt = update
    selected_stage(client, second, 'scene-continuity')
    accept(client, second, selected_ids=['c1', 'c2'])
    current = continuity(client, story['branch_id'])
    assert len(current['entries']) == 2 and len(current['commits']) == 2
    assert current['entries'][0]['text'] == 'The letter remains sealed.'
    assert current['entries'][1]['status'] == 'resolved'
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    earlier = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': branch['revision'], 'node_id': receipt['node_id'], 'name': 'Earlier facts'}).json()
    assert continuity(client, earlier['branch_id']) == original
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = continuity(client, mapping[story['branch_id']])
    assert [(item['id'], item['text'], item['status']) for item in copied['entries']] == [
        (item['id'], item['text'], item['status']) for item in current['entries']]
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})


def test_writer_review_and_collaborator_receive_only_accepted_path_continuity(client, story):
    run_id, provider = ready_continuity(client, story)
    provider.corrupt = lambda result: result['changes'][0].update(kind='knowledge', subject='Wren', text='Wren knows the letter is sealed.')
    selected_stage(client, run_id, 'scene-continuity')
    receipt = accept(client, run_id)
    with client.app.state.database.connect() as connection:
        body = GenerateRequest(operation_id=uuid4().hex, expected_revision=2, use_prepared_beat=False)
        snapshot, _ = generation_snapshot(connection, story['branch_id'], body)
        context = decode(snapshot['content'])
        assert context['continuity']['entries'][0]['kind'] == 'knowledge'
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        sources = branch_sources(connection, branch)
        accepted = ''.join(item['text'] for item in sources if item['id'].startswith('continuity:'))
        assert 'Wren knows' in accepted and 'The choice remains open.' not in accepted
        story_row = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        earlier, node = context['history'][:1], context['history'][-1]
        before = scoped_sources(connection, ROLE_MAP['review-continuity'], story_row, [], earlier, earlier)
        after = scoped_sources(connection, ROLE_MAP['review-continuity'], story_row, earlier, [node], context['history'])
        blind = scoped_sources(connection, ROLE_MAP['review-pacing'], story_row, earlier, [node], context['history'])
    assert not any(item['kind'] == 'accepted continuity' for item in before + blind)
    assert any(item['kind'] == 'accepted continuity' for item in after)
    assert receipt['node_id'] == node['id']


def test_explicit_comparison_can_accept_prose_without_structured_changes(client, story):
    run_id, _ = ready_continuity(client, story)
    profiles = [make_profile(client, name)['profile_id'] for name in ('Continuity A', 'Continuity B')]
    jobs = run_stage(client, run_id, 'scene-continuity', profiles)
    assert all(job['status'] == 'done' for job in jobs)
    assert jobs[0]['snapshot']['content'] == jobs[1]['snapshot']['content']
    choose(client, run_id, jobs[1])
    receipt = accept(client, run_id, selected_ids=[], include_summary=False)
    assert receipt['proposal_job_id'] == jobs[1]['id']
    view = continuity(client, story['branch_id'])
    assert view['entries'] == [] and view['commits'][0]['summary'] == ''
    assert client.get(f"/api/branches/{story['branch_id']}").json()['head_id'] == receipt['node_id']


@pytest.mark.parametrize('damage', ['orphan', 'branch', 'role'])
def test_import_rejects_acceptance_with_missing_or_wrong_provenance(client, story, damage):
    run_id, _ = ready_continuity(client, story)
    receipt = accept(client, run_id)
    _, document = backup(client, story)
    corrupt = deepcopy(document)
    node = next(row for row in corrupt['data']['nodes'] if row['id'] == receipt['node_id'])
    if damage == 'orphan':
        node['id'] = uuid4().hex
        corrupt['data']['nodes'].append({**node, 'id': receipt['node_id']})
    elif damage == 'branch':
        corrupt['data']['branches'][0]['head_id'] = node['parent_id']
    else:
        node['role'] = 'user'
    staged = client.post('/api/archives/imports', json={'content': encode(corrupt)})
    assert staged.status_code == 400, staged.text
