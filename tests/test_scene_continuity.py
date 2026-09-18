import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.database import decode, encode
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_scene_patches import ready_patch, selected_stage
from tests.test_scenes import choose, get_plan, run_stage


class ContinuityProvider:
    """Explicitly labeled fixture output; no production fallback."""
    def __init__(self):
        self.corrupt = None

    async def generate(self, _profile, _prompt, content):
        context = decode(content)
        quote = next(item['text'] for item in context['sources'] if item['id'] == 'scene:checked')
        changes = [{'id': 'c1', 'action': 'add', 'target_id': None, 'kind': 'fact', 'subject': 'The letter',
                    'text': 'The letter is sealed.', 'reason': 'Fixture established state.',
                    'evidence': [{'source_id': 'scene:checked', 'quote': quote}]},
                   {'id': 'c2', 'action': 'add', 'target_id': None, 'kind': 'thread', 'subject': 'The invitation',
                    'text': 'The choice remains open.', 'reason': 'Fixture unresolved choice.',
                    'evidence': [{'source_id': 'scene:checked', 'quote': quote}]}]
        result = {'summary': 'Continuity test fixture only.', 'scene_summary': 'Wren waits beside the sealed letter.',
                  'summary_quote': quote, 'changes': changes}
        if self.corrupt:
            self.corrupt(result)
        yield ProviderEvent(text=encode(result), done=True)


def ready_continuity(client, story, dialogue=False):
    run_id, _ = ready_patch(client, story, dialogue)
    selected_stage(client, run_id, 'scene-patch')
    if dialogue:
        selected_stage(client, run_id, 'scene-dialogue-patch')
    selected_stage(client, run_id, 'scene-patch-check')
    provider = ContinuityProvider()
    client.app.state.scene_runner.provider = provider
    selected_stage(client, run_id, 'scene-continuity')
    return run_id, provider


def acceptance_body(client, run_id, **extra):
    return {'operation_id': uuid4().hex, 'expected_revision': get_plan(client, run_id)['revision'],
            'selected_ids': ['c1'], 'include_summary': True, **extra}


def continuity(client, branch_id):
    return client.get(f'/api/branches/{branch_id}/continuity').json()


def test_scene_acceptance_is_explicit_atomic_and_branch_scoped(client, story):
    run_id, _ = ready_continuity(client, story, dialogue=True)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert continuity(client, story['branch_id']) == {'entries': [], 'commits': []}
    selected = get_plan(client, run_id)
    body = acceptance_body(client, run_id)
    response = client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert response.status_code == 200, response.text
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).json() == response.json()
    receipt = response.json()['state']['accepted']
    after = client.get(f"/api/branches/{story['branch_id']}").json()
    assert after['revision'] == before['revision'] + 1
    assert after['messages'][-1]['text'] == selected['patch']['text']
    assert after['messages'][-1]['id'] == receipt['node_id']
    view = continuity(client, story['branch_id'])
    assert [item['text'] for item in view['entries']] == ['The letter is sealed.']
    assert len(view['commits']) == 1 and view['commits'][0]['summary']
    earlier = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': after['revision'], 'node_id': before['head_id'], 'name': 'Before acceptance'}).json()
    assert continuity(client, earlier['branch_id']) == {'entries': [], 'commits': []}
    edited = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': after['revision'], 'node_id': receipt['node_id'],
        'replacement': 'An alternate scene.', 'name': 'Historical correction'}).json()
    assert continuity(client, edited['branch_id']) == {'entries': [], 'commits': []}
    denied = client.post(f'/api/scenes/{run_id}/choose', json={'operation_id': uuid4().hex,
        'expected_revision': response.json()['revision'], 'job_id': receipt['proposal_job_id']})
    assert denied.status_code == 409


def test_stale_acceptance_needs_an_explicit_new_branch(client, story):
    run_id, _ = ready_continuity(client, story)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    append(client, story['branch_id'], 'A different future.', before['revision'])
    body = acceptance_body(client, run_id)
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).status_code == 409
    body.update(as_new_branch=True, branch_name='Preserved scene')
    result = client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert result.status_code == 200, result.text
    receipt = result.json()['state']['accepted']
    assert receipt['branch_id'] != story['branch_id']
    assert continuity(client, story['branch_id'])['entries'] == []
    branch = client.get(f"/api/branches/{receipt['branch_id']}").json()
    assert 'A different future.' not in [item['text'] for item in branch['messages']]
    assert branch['messages'][-1]['parent_id'] == before['head_id']


def test_continuity_archive_preserves_frozen_inputs_receipt_and_original_ids(client, story):
    run_id, _ = ready_continuity(client, story)
    response = client.post(f'/api/scenes/{run_id}/accept', json=acceptance_body(client, run_id))
    assert response.status_code == 200, response.text
    prior = continuity(client, story['branch_id'])
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    copied = continuity(client, mapping[story['branch_id']])
    assert copied['entries'][0]['id'] == prior['entries'][0]['id']
    assert copied['entries'][0]['node_id'] == mapping[prior['entries'][0]['node_id']]
    new_run = get_plan(client, mapping[run_id])
    assert new_run['state']['accepted']['commit_id'] == mapping[prior['commits'][0]['id']]
    old_inputs = {job['id']: job['snapshot']['content'] for job in get_plan(client, run_id)['jobs']}
    assert all(job['snapshot']['content'] == old_inputs[old] for old in old_inputs for job in new_run['jobs'] if job['id'] == mapping[old])
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    corrupt = deepcopy(document)
    corrupt['data']['continuity_commits'][0]['summary'] = 'Unapproved future.'
    assert client.post('/api/archives/imports', json={'content': json.dumps(corrupt)}).status_code == 400


def test_acceptance_rollback_does_not_leave_prose_or_canon(client, story, monkeypatch):
    run_id, _ = ready_continuity(client, story)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    body = acceptance_body(client, run_id)
    from server.scenes import acceptance
    original = acceptance.touch_branch

    def crash(*_args):
        raise RuntimeError('Fixture: crash after prose insertion before commit')

    monkeypatch.setattr(acceptance, 'touch_branch', crash)
    with pytest.raises(RuntimeError, match='Fixture: crash'):
        client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert continuity(client, story['branch_id'])['commits'] == []
    monkeypatch.setattr(acceptance, 'touch_branch', original)
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).status_code == 200


@pytest.mark.parametrize('corruption', ['quote', 'foreign', 'duplicate'])
def test_invalid_continuity_proposals_preserve_output_and_current_selection(client, story, corruption):
    run_id, provider = ready_continuity(client, story)
    selected = get_plan(client, run_id)['state']['selections']['scene-continuity']
    edits = {'quote': lambda result: result['changes'][0]['evidence'][0].update(quote='Never stated.'),
             'foreign': lambda result: result['changes'][0].update(action='replace', target_id='foreign-future'),
             'duplicate': lambda result: result['changes'].append(deepcopy(result['changes'][0]))}
    provider.corrupt = edits[corruption]
    failed = run_stage(client, run_id, 'scene-continuity')[0]
    assert failed['status'] == 'error' and failed['output']
    assert get_plan(client, run_id)['state']['selections']['scene-continuity'] == selected
    assert continuity(client, story['branch_id'])['commits'] == []


def test_reselecting_patch_invalidates_the_continuity_proposal(client, story):
    run_id, _ = ready_continuity(client, story)
    run = get_plan(client, run_id)
    job = next(job for job in run['jobs'] if job['id'] == run['state']['selections']['scene-patch-check'])
    choose(client, run_id, job)
    assert 'scene-continuity' not in get_plan(client, run_id)['state']['selections']
    assert client.post(f'/api/scenes/{run_id}/accept', json=acceptance_body(client, run_id)).status_code == 409
