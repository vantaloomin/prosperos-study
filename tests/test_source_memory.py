import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.errors import DomainError
from server.memory.budget import token_estimate
from server.memory.source_packet import assemble_sources
from server.memory.source_replay import replay_sources
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_memory import fixture_context, long_story, profiles, small_profile
from tests.test_reviews import ReviewProvider, finished_review, start
from tests.test_scene_continuity import ContinuityProvider, acceptance_body
from tests.test_scene_drafting import PROSE, DraftProvider
from tests.test_scene_patches import PatchProvider, selected_stage
from tests.test_scene_reviews import scene_body
from tests.test_scene_revisions import RevisionProvider, rejected_claim
from tests.test_scenes import choose, decide, get_plan, legacy_scene_creation, run_stage


def source_context():
    source = fixture_context()
    history = [{'id': f"message:{node['id']}", 'title': 'narrator contribution', 'kind': 'accepted', 'text': node['text']}
               for node in source['history']]
    fixed = [{'id': 'draft', 'kind': 'draft', 'title': 'Proposed scene', 'text': 'Mara unlocks the observatory.'},
             {'id': 'ooc', 'kind': 'accepted', 'title': 'ooc contribution', 'text': 'Keep the eclipse quiet.'},
             {'id': 'reference', 'kind': 'reference', 'title': 'Pinned Canon', 'text': 'Ivo owns the observatory.'}]
    def placement(place):
        return {'id': place, 'kind': 'world reference', 'title': place, 'text': place, 'placement': place}
    return {'stage': 'scene-draft', 'director_direction': source['direction'],
            'sources': [placement('header'), *history, placement('recent'), *fixed, placement('tail')],
            'blocks': [{'id': 'p1', 'kind': 'prose', 'text': 'An intact working draft.'}]}


def saved(context, packet, receipt):
    return {'content': encode(packet), 'source_memory': receipt}


def test_source_memory_preserves_exact_required_material_order_and_comparison_budget():
    original = source_context()
    preserved = deepcopy(original)
    packet, memory = assemble_sources(original, 'Write carefully.', profiles(4096, 8192), {'mode': 'long'})
    assert original == preserved and packet['blocks'] == original['blocks']
    assert packet['sources'][0] == original['sources'][0] and packet['sources'][-1] == original['sources'][-1]
    assert all(source in packet['sources'] for source in original['sources'][-5:])
    assert token_estimate('Write carefully.', packet) + memory['overhead_margin'] <= 4096 - 512
    assert not memory['coverage']['complete_history'] and memory['coverage']['recalled_passages'] > 0
    excerpt = next(source for source in packet['sources'] if source.get('source_id') == 'message:n0')
    assert excerpt['text'] in original['sources'][1]['text']
    assert excerpt['sha256'] == hashlib.sha256(excerpt['text'].encode()).hexdigest()
    assert replay_sources(original, saved(original, packet, memory)) == packet


@pytest.mark.parametrize('mode,scope', [('full', 'rules'), ('long', 'blind')])
def test_source_memory_does_not_change_full_context_or_blind_review(mode, scope):
    context = {**source_context(), 'scope': scope}
    packet, memory = assemble_sources(context, 'Review.', profiles(4096), {'mode': mode})
    assert packet is context and memory is None


def test_exact_targets_cannot_be_trimmed_to_fit_and_cited_old_evidence_is_required():
    context = source_context()
    context['findings'] = [{'source_id': 'message:n12', 'quote': context['sources'][13]['text']}]
    packet, _ = assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})
    assert context['sources'][13] in packet['sources']
    context['blocks'][0]['text'] *= 1000
    with pytest.raises(DomainError, match='exact working material'):
        assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})


@pytest.mark.parametrize('tamper', ['remove-draft', 'change-prose', 'overlap', 'coverage', 'blind'])
def test_archive_projection_rejects_missing_targets_altered_evidence_and_false_coverage(tamper):
    context = source_context()
    packet, memory = assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})
    snapshot = saved(context, packet, memory)
    selection = memory['selection']
    if tamper == 'remove-draft':
        selection[:] = [item for item in selection if context['sources'][item['index']]['id'] != 'draft']
    elif tamper == 'change-prose':
        snapshot['content'] += ' '
    elif tamper == 'overlap':
        excerpt = next(item for item in selection if 'start' in item)
        selection.insert(selection.index(excerpt), dict(excerpt))
    elif tamper == 'coverage':
        memory['coverage']['complete_history'] = True
    else:
        context['scope'] = 'blind'
    with pytest.raises(DomainError):
        replay_sources(context, snapshot)


def test_long_historical_review_comparison_retains_exact_target_excludes_future_and_replays(client):
    first = small_profile(client)
    second = small_profile(client, 'Second', 8192)
    story, nodes = long_story(client)
    append(client, story['branch_id'], 'FUTURE FORBIDDEN orchid clue.', len(nodes))
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    body = {'expected_revision': len(nodes) + 1, 'from_node_id': nodes[-1], 'through_node_id': nodes[-1],
            'steps': [{'key': 'review-continuity', 'profile_ids': [first['profile_id'], second['profile_id']]},
                      {'key': 'review-pacing'}]}
    result, _ = start(client, story, body)
    review = finished_review(client, result['id'])
    jobs = review['jobs']
    assert all(job['status'] == 'done' for job in jobs)
    privileged = [job for job in jobs if job['step'] == 'review-continuity']
    assert privileged[0]['snapshot']['content'] == privileged[1]['snapshot']['content']
    assert privileged[0]['snapshot']['source_memory']['coverage']['complete_history'] is False
    for job in jobs:
        content = decode(job['snapshot']['content'])
        assert content['sources'][0]['text'] == fixture_context()['history'][-1]['text']
        assert 'FUTURE FORBIDDEN' not in job['snapshot']['content']
    blind = next(job for job in jobs if job['step'] == 'review-pacing')
    assert 'source_memory' not in blind['snapshot'] and len(decode(blind['snapshot']['content'])['sources']) == 3
    archive, _ = backup(client, story)
    _, mapping = restore(client, archive)
    restored = client.get(f"/api/reviews/{mapping[review['id']]}").json()
    assert [job['snapshot']['content'] for job in restored['jobs']] == [job['snapshot']['content'] for job in jobs]


def set_memory(client, story, mode):
    current = client.get(f"/api/stories/{story['story_id']}").json()
    result = client.put(f"/api/stories/{story['story_id']}", json={
        'expected_revision': current['revision'], 'title': current['title'], 'premise': current['premise'],
        'settings': {**current['settings'], 'memory': {'mode': mode}}})
    assert result.status_code == 200, result.text


def create_long_scene(client, story, revision):
    client.app.state.scene_runner.provider = DraftProvider()
    with legacy_scene_creation():
        response = client.post(f"/api/branches/{story['branch_id']}/scenes", json={
            'expected_revision': revision, 'operation_id': uuid4().hex, 'title': 'Observatory encounter',
            'direction': 'Remember the promise about the brass observatory key.', 'propose_options': False})
    assert response.status_code == 201, response.text
    return response.json()['id']


class EvidenceReviewer:
    async def generate(self, _profile, _prompt, content):
        sources = decode(content)['sources']
        source = next(source for source in sources if source.get('start') is not None)
        findings = [{'severity': severity, 'source_id': source['id'], 'quote': source['text'],
                     'explanation': 'Fixture evidence handoff.', 'suggestion': 'Keep the open decision.'}
                    for severity in ('soft', 'hold', 'hard')]
        yield ProviderEvent(text=encode({'summary': 'Exact retrieved evidence fixture.', 'findings': findings}), done=True)


def test_scene_frozen_memory_review_evidence_survives_revision_patch_continuity_and_archive(client):
    small_profile(client, limit=8192)
    story, nodes = long_story(client)
    scene_id = create_long_scene(client, story, len(nodes))
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    set_memory(client, story, 'full')
    for key in ('scene-beats', 'scene-brief'):
        job = run_stage(client, scene_id, key)[0]
        assert job['status'] == 'done', job['error']
        assert job['snapshot']['source_memory']['mode'] == 'long'
        choose(client, scene_id, job)
    decide(client, scene_id, 'approve')
    for key in ('scene-draft', 'scene-coverage'):
        selected_stage(client, scene_id, key)
    client.app.state.review_runner.provider = EvidenceReviewer()
    request = scene_body(client, scene_id, [{'key': 'review-continuity'}])
    review, _ = start(client, story, request)
    report = finished_review(client, review['id'])['jobs'][0]
    assert report['status'] == 'done', report['error']
    cited = report['result']['findings'][0]['source_id']
    assert decode(report['snapshot']['content'])['sources'][0]['text'] == PROSE
    client.app.state.scene_runner.provider = RevisionProvider()
    triage = run_stage(client, scene_id, 'scene-triage', review_job_ids=[report['id']])[0]
    assert triage['status'] == 'done', triage['error']
    assert any(source['id'] == cited for source in decode(triage['snapshot']['content'])['sources'])
    choose(client, scene_id, triage)
    rejected_claim(client, scene_id)
    decide(client, scene_id, 'approve-revision', {'package': 'C', 'confirmed_hold_ids': ['t2']})
    client.app.state.scene_runner.provider = PatchProvider()
    patch = selected_stage(client, scene_id, 'scene-patch')
    assert any(source['id'] == cited for source in decode(patch['snapshot']['content'])['sources'])
    selected_stage(client, scene_id, 'scene-patch-check')
    client.app.state.scene_runner.provider = ContinuityProvider()
    selected_stage(client, scene_id, 'scene-continuity')
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    accepted = client.post(f'/api/scenes/{scene_id}/accept', json=acceptance_body(client, scene_id))
    assert accepted.status_code == 200, accepted.text
    assert client.get(f"/api/branches/{story['branch_id']}").json()['revision'] == len(nodes) + 1
    archive, _ = backup(client, story)
    restored, mapping = restore(client, archive)
    copied = get_plan(client, mapping[scene_id])
    original = get_plan(client, scene_id)
    assert [job['snapshot']['content'] for job in copied['jobs']] == [job['snapshot']['content'] for job in original['jobs']]
    second, _ = backup(client, {'story_id': restored['story_ids'][0], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


def test_legacy_scene_without_memory_policy_keeps_full_context_when_story_uses_long(client, monkeypatch):
    from server.scenes import service
    original = service.create_snapshot

    def legacy_snapshot(*args):
        snapshot = original(*args)
        snapshot.pop('memory_policy')
        return snapshot

    monkeypatch.setattr(service, 'create_snapshot', legacy_snapshot)
    small_profile(client, limit=8192)
    story, nodes = long_story(client)
    scene_id = create_long_scene(client, story, len(nodes))
    response = client.post(f'/api/scenes/{scene_id}/preview', json={'expected_revision': 0, 'key': 'scene-beats'})
    assert response.status_code == 409 and 'No sources were silently dropped' in response.json()['detail']
    assert get_plan(client, scene_id)['jobs'] == []
