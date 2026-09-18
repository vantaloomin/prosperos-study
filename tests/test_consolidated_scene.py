from copy import deepcopy

from server.database import decode, encode
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_reviews import finished_review, start
from tests.test_scenes import PLAN, choose, decide, get_plan, run_stage, setup_plan


class ConsolidatedProvider:
    """Deterministic protocol fixture; call counts are not live-model quality claims."""
    def __init__(self):
        self.calls = []

    async def generate(self, profile, prompt, content):
        context = decode(content)
        self.calls.append((profile, prompt, content))
        yield ProviderEvent(text=encode(consolidated_output(context)), done=True)


def consolidated_output(context):
    if context.get('reader_contract') == 2:
        return reader_output(context)
    stage = context['stage']
    if stage == 'scene-options':
        return {'summary': 'Fixture alternatives.', 'options': [
            {'id': key, 'title': key, 'direction': 'Consider the letter.', 'opens': 'A conversation.', 'closes': 'Departure.'}
            for key in 'ABCD']}
    if stage == 'scene-beats':
        return deepcopy(PLAN)
    if stage == 'scene-draft':
        return {'summary': 'Fixture scene.', 'blocks': [
            {'id': 'p1', 'kind': 'prose', 'text': 'Wren waits beside the sealed letter, still waiting.'},
            {'id': 'd1', 'kind': 'dialogue', 'speaker': 'Wren', 'instruction': 'Invite an answer without choosing it.'}], 'proposed_facts': []}
    if stage == 'scene-dialogue':
        return {'summary': 'Fixture dialogue.', 'lines': [{'slot_id': 'd1', 'text': 'Would you like to look?'}]}
    if stage == 'scene-triage':
        return {'summary': 'Fixture accountable change.', 'approach': 'patch', 'items': [
            {'id': 't1', 'finding_ids': [item['id'] for item in context['findings']], 'disposition': 'fix',
             'reason': 'Remove the repeated wait and shorten the invitation.', 'action': 'Tighten both blocks.', 'evidence': []}]}
    if stage == 'scene-patch':
        return patch_output(context)
    quote = next(source['text'] for source in context['sources'] if source['id'] == 'scene:checked')
    return {'summary': 'Fixture continuity.', 'scene_summary': 'The letter stays sealed; the invitation remains open.',
            'summary_quote': quote, 'changes': []}


def reader_output(context):
    source = context['sources'][0]
    result = {'summary': 'Fixture reader; exact sources only.', 'findings': []}
    if context['scope'] == 'blind':
        result['findings'] = [{'lens': 'cuts', 'severity': 'cut', 'source_id': source['id'],
                               'quote': 'still waiting', 'explanation': 'The wait is repeated.', 'suggestion': 'Shorten it.'}]
    if context.get('approved_beats'):
        result['coverage'] = [{'beat_id': beat['id'], 'status': 'rendered', 'quotes': ['sealed letter'],
                               'explanation': 'The letter is shown; the player has not acted.'} for beat in context['approved_beats']['beats']]
    return result


def patch_output(context):
    return {'summary': 'Fixture unified patch.', 'edits': [
        {'block_id': block['id'], 'operation': 'replace', 'kind': block['kind'], 'before': block['text'],
         'after': 'Wren waits beside the sealed letter.' if block['kind'] == 'prose' else 'Will you look?',
         'anchor_id': None, 'speaker': '', 'item_ids': ['t1'], 'reason': 'The approved tightening.'}
        for block in context['blocks']],
        'resolutions': [{'item_id': 't1', 'status': 'addressed', 'reason': 'Both approved blocks were tightened.'}]}


def selected(client, scene_id, key, **targets):
    job = run_stage(client, scene_id, key, **targets)[0]
    assert job['status'] == 'done', job['error']
    choose(client, scene_id, job, 'A' if key == 'scene-options' else None)
    return job


def drafted_scene(client, story):
    scene_id, _ = setup_plan(client, story, dialogue=True, legacy=False)
    provider = ConsolidatedProvider()
    client.app.state.scene_runner.provider = provider
    client.app.state.review_runner.provider = provider
    for key in ('scene-options', 'scene-beats'):
        selected(client, scene_id, key)
    assert get_plan(client, scene_id)['next_step'] is None
    decide(client, scene_id, 'approve')
    for key in ('scene-draft', 'scene-dialogue'):
        selected(client, scene_id, key)
    return scene_id, provider


def scene_readers(client, story, scene_id):
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    request = {'expected_revision': branch['revision'], 'scene_id': scene_id,
               'scene_revision': get_plan(client, scene_id)['revision'],
               'steps': [{'key': 'review-blind'}, {'key': 'review-informed'}]}
    created, _ = start(client, story, request)
    review = finished_review(client, created['id'])
    assert len(review['jobs']) == 2
    for job in review['jobs']:
        assert job['status'] == 'done', job['error']
        response = client.put(f"/api/reviews/{created['id']}/selection", json={'job_id': job['id']})
        assert response.status_code == 200, response.text
    return review


def test_default_split_scene_takes_nine_calls_and_restores_exact_inputs(client, story):
    scene_id, provider = drafted_scene(client, story)
    review = scene_readers(client, story, scene_id)
    assert get_plan(client, scene_id)['coverage_passes']
    selected(client, scene_id, 'scene-triage', review_job_ids=[job['id'] for job in review['jobs']])
    decide(client, scene_id, 'approve-revision', {'package': 'B'})
    selected(client, scene_id, 'scene-patch')
    patch = get_plan(client, scene_id)['patch']
    assert patch['checked'] and patch['check_kind'] == 'director' and patch['check'] is None
    assert [item['kind'] for item in patch['blocks']] == ['prose', 'dialogue']
    selected(client, scene_id, 'scene-continuity')
    assert len(provider.calls) == 9
    before = get_plan(client, scene_id)
    assert len(before['jobs']) == 7
    assert not {'scene-brief', 'scene-coverage', 'scene-verify', 'scene-dialogue-patch', 'scene-patch-check'} & {job['step'] for job in before['jobs']}
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert len(branch['messages']) == 1
    decide(client, scene_id, 'accept', {'selected_ids': [], 'include_summary': True})
    assert len(provider.calls) == 9
    record, _ = backup(client, story)
    _, mapping = restore(client, record)
    restored = get_plan(client, mapping[scene_id])
    original_content = {job['id']: job['snapshot']['content'] for job in before['jobs']}
    assert all(job['snapshot']['content'] == original_content[old] for old, new in mapping.items()
               for job in restored['jobs'] if job['id'] == new and old in original_content)
    blind, informed = [decode(job['snapshot']['content']) for job in review['jobs']]
    assert set(blind) == {'task', 'role', 'scope', 'sources', 'reader_contract', 'lenses'}
    assert all(source['kind'] in {'draft', 'previous'} for source in blind['sources'])
    assert 'approved_beats' in informed and all(source['kind'] != 'chance' for source in informed['sources'])
