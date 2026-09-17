import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile
from tests.test_reviews import finished_review, start
from tests.test_scene_drafting import DraftProvider
from tests.test_scene_reviews import reviewable_plan, scene_body
from tests.test_scenes import choose, decide, finish_plan, get_plan, run_stage


class RevisionReviewProvider:
    async def generate(self, _profile, _prompt, content):
        source = decode(content)['sources'][0]
        findings = [{'severity': severity, 'source_id': source['id'], 'quote': source['text'],
                     'explanation': f'Fixture {severity} finding.', 'suggestion': 'Keep the decision open.'}
                    for severity in ('soft', 'hold', 'hard')]
        yield ProviderEvent(text=encode({'summary': 'Review fixture only.', 'findings': findings}), done=True)


class RevisionProvider:
    def __init__(self):
        self.calls, self.corrupt = [], None

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        context = decode(content)
        result = revision_fixture(context)
        if self.corrupt:
            self.corrupt(result)
        yield ProviderEvent(text=encode(result), done=True)


def revision_fixture(context):
    if context['stage'] == 'scene-verify':
        source = context['sources'][0]
        return {'summary': 'Fixture verdict: preserve uncertainty.', 'verdict': 'rejected',
                'evidence': [{'source_id': source['id'], 'quote': source['text']}], 'smallest_fix': ''}
    items = [{'id': f't{index + 1}', 'finding_ids': [finding['id']], 'disposition': disposition,
              'reason': 'Fixture proposed disposition.', 'action': 'Preserve the open decision.', 'evidence': []}
             for index, (finding, disposition) in enumerate(zip(context['findings'], ('verify', 'hold', 'hard-fix'), strict=True))]
    return {'summary': 'Triage fixture only; no model called.', 'approach': 'patch', 'items': items}


def revision_ready(client, story, dialogue=False):
    run_id, _ = reviewable_plan(client, story, dialogue)
    client.app.state.review_runner.provider = RevisionReviewProvider()
    review, _ = start(client, story, scene_body(client, run_id))
    reports = finished_review(client, review['id'])
    provider = RevisionProvider()
    client.app.state.scene_runner.provider = provider
    return run_id, reports, provider


def triage_ready(client, story, dialogue=False):
    run_id, reports, provider = revision_ready(client, story, dialogue)
    job = run_stage(client, run_id, 'scene-triage', review_job_ids=[reports['jobs'][0]['id']])[0]
    assert job['status'] == 'done', job['error']
    choose(client, run_id, job)
    return run_id, reports, provider


def rejected_claim(client, run_id):
    verdict = run_stage(client, run_id, 'scene-verify', item_id='t1')[0]
    assert verdict['status'] == 'done', verdict['error']
    choose(client, run_id, verdict)
    resolution = {'disposition': 'overrule', 'reason': 'The quoted context leaves the choice open.',
                  'action': '', 'evidence': verdict['result']['evidence']}
    decide(client, run_id, 'resolve', {'item_id': 't1', 'resolution': resolution})


def gate_request(client, run_id, **changes):
    return client.post(f'/api/scenes/{run_id}/approve-revision', json={
        'operation_id': uuid4().hex, 'expected_revision': get_plan(client, run_id)['revision'], 'package': 'B', **changes})


def test_triage_verification_and_gate_b_preserve_story_and_require_structural_confirmation(client, story):
    run_id, reports, _ = triage_ready(client, story)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert client.get(f"/api/reviews/{reports['id']}").json()['current_scene_draft']
    assert gate_request(client, run_id).status_code == 409
    rejected_claim(client, run_id)
    run = get_plan(client, run_id)
    assert run['revision_plan']['packages'] == {'A': ['t3'], 'B': ['t3'], 'C': ['t2', 't3']}
    assert gate_request(client, run_id, package='custom', item_ids=['t2']).status_code == 400
    assert gate_request(client, run_id, package='C').status_code == 400
    approved = decide(client, run_id, 'approve-revision', {'package': 'C', 'confirmed_hold_ids': ['t2']})
    assert approved['state']['gate_b']['item_ids'] == ['t2', 't3']
    assert gate_request(client, run_id).status_code == 409
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before


def test_triage_comparison_and_stale_targets_cannot_be_selected(client, story):
    run_id, reports, _ = revision_ready(client, story)
    profiles = [make_profile(client, label)['profile_id'] for label in ('First triager', 'Second triager')]
    jobs = run_stage(client, run_id, 'scene-triage', profiles, review_job_ids=[reports['jobs'][0]['id']])
    assert jobs[0]['snapshot']['content'] == jobs[1]['snapshot']['content']
    client.app.state.scene_runner.provider = DraftProvider()
    choose(client, run_id, run_stage(client, run_id, 'scene-draft')[0])
    response = client.post(f'/api/scenes/{run_id}/choose', json={'expected_revision': get_plan(client, run_id)['revision'],
                          'operation_id': uuid4().hex, 'job_id': jobs[0]['id']})
    assert response.status_code == 409
    choose(client, run_id, run_stage(client, run_id, 'scene-coverage')[0])
    request = {'expected_revision': get_plan(client, run_id)['revision'], 'key': 'scene-triage', 'review_job_ids': [reports['jobs'][0]['id']]}
    assert client.post(f'/api/scenes/{run_id}/preview', json=request).status_code == 409


@pytest.mark.parametrize('corruption', ['missing', 'duplicate', 'hard-downgrade', 'structural-downgrade'])
def test_invalid_triage_is_preserved_as_failed_output(client, story, corruption):
    run_id, reports, provider = revision_ready(client, story)
    modifiers = {'missing': lambda result: result['items'].pop(),
                 'duplicate': lambda result: result['items'].append(deepcopy(result['items'][0])),
                 'hard-downgrade': lambda result: result['items'][-1].update(disposition='fix'),
                 'structural-downgrade': lambda result: result['items'][1].update(disposition='fix')}
    provider.corrupt = modifiers[corruption]
    job = run_stage(client, run_id, 'scene-triage', review_job_ids=[reports['jobs'][0]['id']])[0]
    assert job['status'] == 'error' and job['output'] and job['result'] is None
    assert get_plan(client, run_id)['revision_plan'] is None


def test_invalid_verdict_retry_and_explicit_resolution_preserve_original_inputs(client, story):
    run_id, _, provider = triage_ready(client, story)
    provider.corrupt = lambda result: result.update(evidence=[{'source_id': 'foreign', 'quote': 'invented'}])
    job = run_stage(client, run_id, 'scene-verify', item_id='t1')[0]
    assert job['status'] == 'error'
    provider.corrupt = None
    assert client.post(f"/api/scene-jobs/{job['id']}/retry").status_code == 200
    retried = next(item for item in finish_plan(client, run_id)['jobs'] if item['id'] == job['id'])
    assert retried['status'] == 'done' and retried['snapshot'] == job['snapshot']
    assert len(client.get(f"/api/scene-jobs/{job['id']}/attempts").json()) == 2
    choose(client, run_id, retried)
    assert gate_request(client, run_id).status_code == 409


def test_new_draft_clears_gate_b_but_preserves_journal_and_revision_brief(client, story):
    run_id, _, _ = triage_ready(client, story)
    rejected_claim(client, run_id)
    decide(client, run_id, 'approve-revision', {'package': 'B'})
    client.app.state.scene_runner.provider = DraftProvider()
    replacement = run_stage(client, run_id, 'scene-draft')[0]
    assert decode(replacement['snapshot']['content'])['revision_context']['triage']['items']
    choose(client, run_id, replacement)
    run = get_plan(client, run_id)
    assert run['state']['gate_a'] and not run['state']['gate_b'] and not run['state']['verifications']
    assert run['revision_plan'] is None and any(item['kind'] == 'approve-revision' for item in run['decisions'])


def test_structural_hard_fixes_stay_required_and_redraft_cannot_be_approved(client, story):
    run_id, reports, provider = revision_ready(client, story)
    provider.corrupt = lambda result: result['items'][-1].update(disposition='hold')
    job = run_stage(client, run_id, 'scene-triage', review_job_ids=[reports['jobs'][0]['id']])[0]
    choose(client, run_id, job)
    provider.corrupt = None
    rejected_claim(client, run_id)
    assert get_plan(client, run_id)['revision_plan']['packages']['A'] == ['t3']
    assert gate_request(client, run_id, package='A').status_code == 400
    assert gate_request(client, run_id, package='custom', item_ids=[]).status_code == 400
    provider.corrupt = lambda result: result.update(approach='redraft')
    choose(client, run_id, run_stage(client, run_id, 'scene-triage', review_job_ids=[reports['jobs'][0]['id']])[0])
    assert gate_request(client, run_id).status_code == 409


def test_revision_archive_remaps_owned_links_without_rewriting_model_inputs(client, story):
    run_id, _, _ = triage_ready(client, story)
    rejected_claim(client, run_id)
    decide(client, run_id, 'approve-revision', {'package': 'C', 'confirmed_hold_ids': ['t2']})
    old = get_plan(client, run_id)
    archive, document = backup(client, story)
    assert document['version'] == 19
    restored, mapping = restore(client, archive)
    new = get_plan(client, mapping[run_id])
    assert new['state']['gate_b']['triage_job_id'] == mapping[old['state']['gate_b']['triage_job_id']]
    assert new['state']['gate_b']['items'] == old['state']['gate_b']['items']
    assert all(new_job['snapshot']['content'] == old_job['snapshot']['content'] for new_job, old_job in zip(new['jobs'], old['jobs'], strict=True))
    backup(client, {'story_id': restored['story_ids'][0], 'branch_id': mapping[story['branch_id']]})
    bad = deepcopy(document)
    row = bad['data']['scene_runs'][0]
    state = decode(row['state'])
    state['gate_b']['confirmed_hold_ids'] = []
    row['state'] = encode(state)
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400
    bad_output = deepcopy(document)
    triage = next(job for job in bad_output['data']['scene_jobs'] if job['step'] == 'scene-triage')
    output = decode(triage['output'])
    output['summary'] = 'Different saved provider output.'
    triage['output'] = encode(output)
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad_output)}).status_code == 400
