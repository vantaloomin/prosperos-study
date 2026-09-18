from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.errors import DomainError
from server.scenes.revision_models import validate_triage
from server.workflow.runner import parse_review
from tests.test_consolidated_scene import drafted_scene, scene_readers, selected
from tests.test_profiles import make_profile
from tests.test_scenes import get_plan


def test_readers_reject_unselected_lenses_false_quotes_and_excess_findings(client, story):
    scene_id, _ = drafted_scene(client, story)
    review = scene_readers(client, story, scene_id)
    blind = review['jobs'][0]
    valid = blind['result']
    for mutate in (
        lambda result: result['findings'][0].update(lens='rules'),
        lambda result: result['findings'][0].update(quote='invented evidence'),
        lambda result: result.update(findings=result['findings'] * 4),
    ):
        broken = deepcopy(valid)
        mutate(broken)
        with pytest.raises(DomainError):
            parse_review(encode(broken), blind['snapshot']['content'])
    informed = review['jobs'][1]
    for field in ('coverage',):
        broken = deepcopy(informed['result'])
        del broken[field]
        with pytest.raises(DomainError, match='every approved beat'):
            parse_review(encode(broken), informed['snapshot']['content'])
    broken = deepcopy(informed['result'])
    broken['coverage'][0]['quotes'] = ['not in this draft']
    with pytest.raises(DomainError):
        parse_review(encode(broken), informed['snapshot']['content'])


def test_redraft_invalidates_coverage_and_rejects_old_triage_inputs(client, story):
    scene_id, _ = drafted_scene(client, story)
    review = scene_readers(client, story, scene_id)
    selected(client, scene_id, 'scene-draft')
    selected(client, scene_id, 'scene-dialogue')
    run = get_plan(client, scene_id)
    assert not run['coverage_passes']
    response = client.post(f'/api/scenes/{scene_id}/preview', json={
        'expected_revision': run['revision'], 'key': 'scene-triage', 'review_job_ids': [job['id'] for job in review['jobs']]})
    assert response.status_code == 409 and 'exact scene draft' in response.text
    assert client.get(f"/api/reviews/{review['id']}").json()['current_scene_draft'] is False


def test_retained_lens_settings_and_comparison_count_are_explicit(client, story):
    scene_id, provider = drafted_scene(client, story)
    other = make_profile(client, 'Second reader')
    old = client.get('/api/prompts/review-cuts/versions').json()[0]
    assert client.put('/api/prompts/review-cuts', json={'expected_version_id': old['id'], 'template': 'Keep my cuts lens.'}).status_code == 200
    response = client.post(f"/api/branches/{story['branch_id']}/reviews/preview", json={
        'expected_revision': 1, 'scene_id': scene_id, 'scene_revision': get_plan(client, scene_id)['revision'],
        'steps': [{'key': 'review-blind', 'lenses': ['cuts', 'pacing'], 'profile_ids': [other['profile_id']]}]})
    assert response.status_code == 200, response.text
    assert response.json()['request_count'] == 2
    assert [job['step'] for job in response.json()['jobs']] == ['review-blind', 'review-cuts']
    assert len(provider.calls) == 4  # Preview made no provider request.
    task = next(item for item in client.get('/api/prompts').json() if item['key'] == 'review-blind')['tasks']
    saved = next(item for item in task if item['key'] == 'review-cuts')
    adopted = client.post('/api/prompts/review-cuts/adopt-combined', json={'expected_version_id': saved['prompt_id']})
    assert adopted.status_code == 200
    assert any(item['template'] == 'Keep my cuts lens.' for item in client.get('/api/prompts/review-cuts/versions').json())


def test_undecidable_requires_author_resolution_and_verify_is_legacy_only(client, story):
    scene_id, _ = drafted_scene(client, story)
    review = scene_readers(client, story, scene_id)
    job = selected(client, scene_id, 'scene-triage', review_job_ids=[item['id'] for item in review['jobs']])
    context = decode(job['snapshot']['content'])
    result = deepcopy(job['result'])
    result['items'][0].update(disposition='undecidable', action='', reason='The draft does not establish whether the repetition is intentional.')
    validate_triage(result, context)
    body = {'operation_id': uuid4().hex, 'expected_revision': get_plan(client, scene_id)['revision'],
            'item_id': 't1', 'resolution': {key: value for key, value in result['items'][0].items() if key not in {'id', 'finding_ids'}}}
    assert client.post(f'/api/scenes/{scene_id}/resolve', json=body).status_code == 200
    response = client.post(f'/api/scenes/{scene_id}/approve-revision', json={
        'operation_id': uuid4().hex, 'expected_revision': get_plan(client, scene_id)['revision'], 'package': 'B'})
    assert response.status_code == 409 and 'disputed' in response.text
    result['items'][0]['disposition'] = 'verify'
    with pytest.raises(DomainError, match='inline'):
        validate_triage(result, context)
    result['items'][0].update(disposition='hard-fix', action='Remove the repetition.')
    with pytest.raises(DomainError, match='evidence'):
        validate_triage(result, context)


@pytest.mark.parametrize('stage', ['scene-brief', 'scene-coverage', 'scene-verify', 'scene-dialogue-patch', 'scene-patch-check'])
def test_new_work_rejects_retired_stages(client, story, stage):
    scene_id, _ = drafted_scene(client, story)
    response = client.post(f'/api/scenes/{scene_id}/preview', json={'expected_revision': get_plan(client, scene_id)['revision'], 'key': stage})
    assert response.status_code == 409 and 'consolidated' in response.text
