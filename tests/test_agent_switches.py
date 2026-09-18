import json
from copy import deepcopy
from uuid import uuid4

from tests.prompt_fixtures import saved_prompt
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_scene_drafting import DraftProvider
from tests.test_scenes import choose, decide, get_plan, run_stage, setup_plan


def toggle(client, key, enabled=False):
    row = saved_prompt(client, key)
    response = client.put(f'/api/prompts/{key}/activation', json={'enabled': enabled, 'expected_revision': row['activation_revision']})
    assert response.status_code == 200, response.text
    return row


def test_switches_preserve_prompt_versions_and_reject_stale_updates(client):
    original = toggle(client, 'writer')
    after = saved_prompt(client, 'writer')
    assert not after['enabled'] and after['id'] == original['id'] and after['template'] == original['template']
    assert client.put('/api/prompts/writer/activation', json={'enabled': True, 'expected_revision': original['activation_revision']}).status_code == 409
    assert client.put('/api/prompts/unknown/activation', json={'enabled': False, 'expected_revision': after['activation_revision']}).status_code == 404
    toggle(client, 'writer', True)
    prompts = client.get('/api/prompts').json()
    assert [row['order'] for row in prompts] == sorted(row['order'] for row in prompts)
    assert len({row['key'] for row in prompts}) == len(prompts)


def skipped_scene(client, story):
    for key in ('scene-options', 'scene-beats', 'scene-brief', 'scene-dialogue', 'scene-continuity'):
        toggle(client, key)
    run_id, _ = setup_plan(client, story, dialogue=True)
    provider = DraftProvider()
    client.app.state.scene_runner.provider = provider
    run = get_plan(client, run_id)
    assert run['next_step'] is None and not run['snapshot']['dialogue_split']
    assert 'scene-coverage' in run['snapshot']['disabled_steps']
    decide(client, run_id, 'approve')
    choose(client, run_id, run_stage(client, run_id, 'scene-draft')[0])
    return run_id, provider


def test_disabled_planning_stages_skip_calls_and_manual_acceptance_round_trips(client, story):
    run_id, provider = skipped_scene(client, story)
    run = get_plan(client, run_id)
    assert [json.loads(call[2])['stage'] for call in provider.calls] == ['scene-draft']
    assert run['next_step'] is None and run['draft']['complete']
    assert run['coverage_passes'] is False and run['manual_acceptance']
    body = {'operation_id': uuid4().hex, 'expected_revision': run['revision']}
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).status_code == 409
    receipt = decide(client, run_id, 'accept', {'manual_review': True})['state']['accepted']
    assert receipt['manual_review'] and not receipt.get('commit_id')
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['messages'][-1]['text'] == run['draft']['text']
    assert client.get(f"/api/branches/{story['branch_id']}/continuity").json() == {'entries': [], 'commits': []}
    record, document = backup(client)
    _, mapping = restore(client, record)
    restored = get_plan(client, mapping[run_id])
    assert restored['state']['accepted']['node_id'] == mapping[receipt['node_id']]
    assert restored['coverage_passes'] is False
    corrupt = deepcopy(document)
    corrupt['data']['scene_decisions'][-1]['payload'] = json.dumps({**json.loads(corrupt['data']['scene_decisions'][-1]['payload']), 'manual_review': False})
    assert client.post('/api/archives/imports', json={'content': json.dumps(corrupt)}).status_code == 400


def test_manual_acceptance_requires_complete_draft_and_preserves_stale_branch(client, story):
    run_id, _ = skipped_scene(client, story)
    run = get_plan(client, run_id)
    origin = client.get(f"/api/branches/{story['branch_id']}").json()
    append(client, story['branch_id'], 'A newer direction.', origin['revision'])
    body = {'operation_id': uuid4().hex, 'expected_revision': run['revision'], 'manual_review': True}
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).status_code == 409
    body.update(as_new_branch=True, branch_name='Preserved starting point')
    response = client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['state']['accepted']['branch_id'] != story['branch_id']
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == 'A newer direction.'


def test_disabled_stage_is_blocked_even_if_request_is_sent_directly(client, story):
    run_id, _ = setup_plan(client, story)
    toggle(client, 'scene-options')
    response = client.post(f'/api/scenes/{run_id}/preview', json={'expected_revision': 0, 'key': 'scene-options'})
    assert response.status_code == 409 and 'disabled' in response.text
    assert not get_plan(client, run_id)['jobs']


def test_disabled_scene_writer_has_no_dangling_dialogue_or_coverage_request(client, story):
    toggle(client, 'scene-draft')
    run_id, _ = setup_plan(client, story, options=False, dialogue=True)
    for key in ('scene-beats', 'scene-brief'):
        choose(client, run_id, run_stage(client, run_id, key)[0])
    decide(client, run_id, 'approve')
    run = get_plan(client, run_id)
    assert run['next_step'] is None and run['draft'] is None
    assert run['manual_acceptance'] is None
    response = client.post(f'/api/scenes/{run_id}/accept', json={'operation_id': uuid4().hex, 'expected_revision': run['revision'], 'manual_review': True})
    assert response.status_code == 409


def test_review_batch_omits_disabled_roles_and_rejects_an_empty_batch(client, story):
    from tests.test_profiles import make_profile
    make_profile(client, 'Primary', primary=True)
    append(client, story['branch_id'], 'The letter is sealed.', 0)
    toggle(client, 'review-continuity')
    body = {'expected_revision': 1, 'steps': [{'key': 'review-continuity'}, {'key': 'review-plausibility'}]}
    endpoint = f"/api/branches/{story['branch_id']}/reviews/preview"
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert [job['step'] for job in response.json()['jobs']] == ['review-plausibility']
    assert response.json()['request_count'] == 1
    toggle(client, 'review-plausibility')
    assert client.post(endpoint, json=body).status_code == 409


def test_disabled_primary_writer_cannot_be_bypassed_by_an_explicit_profile(client, story):
    from tests.test_profiles import make_profile
    profile = make_profile(client, 'Primary', primary=True)
    toggle(client, 'writer')
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'direction': 'Continue.', 'profile_ids': [profile['profile_id']]}
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=body)
    assert response.status_code == 409 and 'disabled' in response.text
