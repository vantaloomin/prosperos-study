import asyncio
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.providers.events import ProviderEvent
from tests.test_agent_switches import toggle
from tests.test_archives import backup, restore
from tests.test_knowledge_references import fixture, grant, sources
from tests.test_memory import small_profile
from tests.test_memory_controls import entry, save
from tests.test_scene_drafting import DraftProvider, approved_plan
from tests.test_scenes import choose, decide, finish_plan, get_plan, run_stage


class CharacterProvider(DraftProvider):
    def __init__(self):
        super().__init__()
        self.fail = False
        self.pause = False

    async def generate(self, profile, prompt, content):
        context = decode(content)
        if context['stage'] == 'scene-draft':
            self.calls.append((profile, prompt, content))
            result = {'summary': 'Fixture narration.', 'proposed_facts': ['NARRATOR_SECRET'], 'blocks': [
                {'id': 'p1', 'kind': 'prose', 'text': 'NARRATOR_SECRET: one character has hidden the letter.'},
                {'id': 's1', 'kind': 'dialogue', 'speaker': 'Elin', 'instruction': 'SLOT_SECRET: distract the other character.'},
                {'id': 's2', 'kind': 'dialogue', 'speaker': 'Other Elin', 'instruction': 'SLOT_SECRET: reveal an unseen fact.'},
                {'id': 's3', 'kind': 'dialogue', 'speaker': 'Elin', 'instruction': 'SLOT_SECRET: force the player to agree.'}]}
        elif context['stage'] == 'scene-coverage':
            self.calls.append((profile, prompt, content))
            result = {'summary': 'Fixture coverage only.', 'beats': [
                {'beat_id': beat['id'], 'status': 'rendered',
                 'quotes': [context['draft']['blocks'][0]['text']], 'explanation': 'Fixture evidence.'}
                for beat in context['proposed_beats']['beats']], 'issues': []}
        elif context['stage'] == 'scene-dialogue':
            self.calls.append((profile, prompt, content))
            slots = [item['id'] for item in context['skeleton']['blocks'] if item['kind'] == 'dialogue']
            if 's2' in slots and self.pause:
                yield ProviderEvent(text='Preserved partial character response.')
                await asyncio.sleep(30)
            if 's2' in slots and self.fail:
                yield ProviderEvent(text='Not valid structured dialogue.', done=True)
                return
            result = {'summary': 'Fixture character response.', 'lines': [{'slot_id': slot, 'text': 'Spoken fixture ' + slot} for slot in slots]}
        else:
            async for event in super().generate(profile, prompt, content):
                yield event
            return
        yield ProviderEvent(text=encode(result), usage={'output_tokens': 23}, done=True)


def ready(client):
    story, first, second, book = fixture(client)
    first_grant = grant(client, story, first, book)
    second_sources = [item for item in sources(client, story['branch_id']) if item['asset_id'] == second['asset_id']]
    second_grant = entry(second_sources, stance='knows', character_id=second['asset_id'], text='SECOND_ONLY interpretation.')
    save(client, story['branch_id'], [first_grant, second_grant])
    run_id, _ = approved_plan(client, story, dialogue=True)
    provider = CharacterProvider()
    client.app.state.scene_runner.provider = provider
    choose(client, run_id, run_stage(client, run_id, 'scene-draft')[0])
    actors = [{'character_id': first['asset_id'], 'slot_ids': ['s3', 's1'], 'briefing': 'VISIBLE_FIRST: ask about the ferry, without deciding for the player.'},
              {'character_id': second['asset_id'], 'slot_ids': ['s2'], 'briefing': 'VISIBLE_SECOND: respond to a question about the ferry.'}]
    return story, run_id, provider, actors


def preview(client, run_id, actors, profiles=None, **extra):
    body = {'key': 'scene-dialogue', 'expected_revision': get_plan(client, run_id)['revision'],
            'dialogue_actors': actors, 'profile_ids': profiles or [], **extra}
    response = client.post('/api/scenes/' + run_id + '/preview', json=body)
    return response, body


def start(client, run_id, actors):
    response, body = preview(client, run_id, actors)
    assert response.status_code == 200, response.text
    request = {**body, 'operation_id': uuid4().hex, 'preview_hash': response.json()['preview_hash']}
    result = client.post('/api/scenes/' + run_id + '/stages', json=request)
    assert result.status_code == 201, result.text
    return result.json()['job_ids'][0]


def test_character_calls_never_receive_full_plan_narration_other_briefings_or_other_knowledge(client):
    story, run_id, provider, actors = ready(client)
    before = client.get('/api/branches/' + story['branch_id']).json()
    report, _ = preview(client, run_id, actors)
    assert report.status_code == 200, report.text
    assert report.json()['request_count'] == 2 and len(provider.calls) == 1
    job = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors)[0]
    assert job['status'] == 'done', job['error']
    first, second = provider.calls[-2:]
    assert 'copper coins' in first[2] and 'measured sentences' in first[2]
    assert 'SECRET' not in first[2] and 'VISIBLE_SECOND' not in first[2] and 'SECOND_ONLY' not in first[2]
    assert 'SECRET different Elin' in second[2] and 'SECOND_ONLY' in second[2]
    assert 'VISIBLE_FIRST' not in second[2] and 'copper coins' not in second[2]
    assert all('NARRATOR_SECRET' not in call[2] and 'SLOT_SECRET' not in call[2] for call in (first, second))
    assert 'NARRATOR_SECRET' in job['snapshot']['content']  # Assembly evidence is internal, never a provider call.
    assert job['snapshot']['dialogue_actors'][0]['slot_ids'] == ['s1', 's3']
    assert [line['slot_id'] for line in job['result']['lines']] == ['s1', 's2', 's3']
    assert not get_plan(client, run_id)['draft']['complete']
    choose(client, run_id, job)
    assert get_plan(client, run_id)['draft']['complete']
    assert client.get('/api/branches/' + story['branch_id']).json() == before
    coverage = run_stage(client, run_id, 'scene-coverage')[0]
    assert coverage['status'] == 'done', coverage['error']
    choose(client, run_id, coverage)
    assert get_plan(client, run_id)['coverage_passes']


def test_profile_comparisons_share_identical_character_packets_and_preview_physical_calls(client):
    _, run_id, provider, actors = ready(client)
    profiles = [small_profile(client, 'Small actor', 4096)['profile_id'], small_profile(client, 'Large actor', 8192)['profile_id']]
    report, _ = preview(client, run_id, actors, profiles)
    assert report.status_code == 200, report.text
    assert report.json()['request_count'] == 4
    jobs = run_stage(client, run_id, 'scene-dialogue', profiles, dialogue_actors=actors)
    assert len(jobs) == 2 and all(job['status'] == 'done' for job in jobs)
    assert jobs[0]['snapshot']['dialogue_actors'] == jobs[1]['snapshot']['dialogue_actors']
    assert all(item['knowledge_lens']['input_allowance'] == 3584 for item in jobs[0]['snapshot']['dialogue_actors'])
    assert len(provider.calls) == 5  # One draft plus four explicit character requests.


@pytest.mark.parametrize('mutation', ['empty', 'missing', 'duplicate', 'foreign', 'view', 'stage'])
def test_invalid_actor_assignments_fail_before_paid_calls_or_records(client, mutation):
    _, run_id, provider, actors = ready(client)
    changes = {}
    if mutation == 'empty':
        actors = []
    elif mutation == 'missing':
        actors = actors[:1]
    elif mutation == 'duplicate':
        actors[1]['slot_ids'].append('s1')
    elif mutation == 'foreign':
        actors[0]['slot_ids'].append('outside-slot')
    elif mutation == 'view':
        actors[0]['character_id'] = 'unattached-character'
    else:
        changes['key'] = 'scene-coverage'
    before = get_plan(client, run_id)
    response, _ = preview(client, run_id, actors, **changes)
    assert response.status_code in {400, 409, 422}
    assert len(provider.calls) == 1 and get_plan(client, run_id) == before


def test_scene_uses_frozen_character_decisions_despite_later_author_changes(client):
    story, run_id, _, actors = ready(client)
    before, _ = preview(client, run_id, actors)
    save(client, story['branch_id'], [])
    after, _ = preview(client, run_id, actors)
    assert after.json() == before.json()
    assert client.get('/api/scenes/' + run_id + '/character-evidence').json()
    job = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors)[0]
    assert job['status'] == 'done'


def test_explicit_retry_keeps_completed_actor_output_and_only_repeats_failed_call(client):
    _, run_id, provider, actors = ready(client)
    provider.fail = True
    failed = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors)[0]
    assert failed['status'] == 'error' and 'structured proposal' in failed['error']
    original = decode(failed['output'])['actors'][0]['output']
    provider.fail = False
    response = client.post('/api/scene-jobs/' + failed['id'] + '/retry', json={})
    assert response.status_code == 200, response.text
    run = finish_plan(client, run_id)
    done = next(job for job in run['jobs'] if job['id'] == failed['id'])
    assert done['status'] == 'done', done['error']
    assert len(provider.calls) == 4  # Draft + first actor + failed second + second retry.
    assert decode(done['output'])['actors'][0]['output'] == original
    assert done['usage']['character_requests'][0]['reused']
    attempts = client.get('/api/scene-jobs/' + done['id'] + '/attempts').json()
    assert len(attempts) == 2 and attempts[-1]['output'] == failed['output']


def test_actor_archive_restores_exact_inputs_completed_responses_and_retry_links_twice(client):
    story, run_id, provider, actors = ready(client)
    provider.fail = True
    failed = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors)[0]
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    provider.fail = False
    response = client.post('/api/scene-jobs/' + mapping[failed['id']] + '/retry', json={})
    assert response.status_code == 200, response.text
    run = finish_plan(client, mapping[run_id])
    done = next(job for job in run['jobs'] if job['id'] == mapping[failed['id']])
    assert done['status'] == 'done', done['error']
    assert len(provider.calls) == 4
    assert [item['content'] for item in done['snapshot']['dialogue_actors']] == [item['content'] for item in failed['snapshot']['dialogue_actors']]
    assert done['snapshot']['dialogue_actors'][0]['knowledge_character_id'] == mapping[actors[0]['character_id']]
    choose(client, mapping[run_id], done)
    file2, _ = backup(client, {key: mapping[value] for key, value in story.items()})
    restore(client, file2)


@pytest.mark.parametrize('mutation', ['extra-input', 'other-identity', 'duplicate-slots', 'assembled-line', 'preserved-output', 'changed-skeleton'])
def test_archive_rejects_actor_scope_and_output_tampering(client, mutation):
    story, run_id, _, actors = ready(client)
    job = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors)[0]
    _, document = backup(client, story)
    row = next(row for row in document['data']['scene_jobs'] if row['id'] == job['id'])
    saved = decode(row['snapshot'])
    first = saved['dialogue_actors'][0]
    if mutation == 'extra-input':
        first['content'] = encode({**decode(first['content']), 'private_background': 'SECRET'})
        first['content_sha256'] = hashlib.sha256(first['content'].encode()).hexdigest()
    elif mutation == 'other-identity':
        first['knowledge_character_id'] = actors[1]['character_id']
    elif mutation == 'duplicate-slots':
        first['slot_ids'].append('s2')
    elif mutation == 'assembled-line':
        result = decode(row['result'])
        result['lines'][0]['text'] = 'A substituted line.'
        row['result'] = encode(result)
    elif mutation == 'changed-skeleton':
        context = decode(saved['content'])
        context['skeleton']['blocks'][0]['text'] = 'Altered selected narration.'
        saved['content'] = encode(context)
    else:
        output = decode(row['output'])
        output['actors'][0]['index'] = 1
        row['output'] = encode(output)
    row['snapshot'] = encode(saved)
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_cancelling_a_character_batch_preserves_completed_actor_and_partial_current_output(client):
    _, run_id, provider, actors = ready(client)
    provider.pause = True
    job_id = start(client, run_id, actors)
    async def wait_for_partial():
        for _ in range(100):
            with client.app.state.database.connect() as connection:
                row = connection.execute('SELECT output FROM scene_jobs WHERE id=?', (job_id,)).fetchone()
                if 'Preserved partial' in row['output']:
                    return
            await asyncio.sleep(.02)
        raise AssertionError('The character request did not reach its partial response.')
    client.portal.call(wait_for_partial)
    assert client.post('/api/scene-jobs/' + job_id + '/cancel', json={}).status_code == 200
    run = finish_plan(client, run_id)
    cancelled = next(job for job in run['jobs'] if job['id'] == job_id)
    assert cancelled['status'] == 'cancelled' and 'Preserved partial' in cancelled['output']
    assert decode(cancelled['output'])['actors'][0]['status'] == 'done'
    provider.pause = False
    assert client.post('/api/scene-jobs/' + job_id + '/retry', json={}).status_code == 200
    done = next(job for job in finish_plan(client, run_id)['jobs'] if job['id'] == job_id)
    assert done['status'] == 'done' and len(provider.calls) == 4


def test_preview_guard_rejects_changed_briefing_without_paid_calls(client):
    _, run_id, provider, actors = ready(client)
    report, body = preview(client, run_id, actors)
    changed = deepcopy(body)
    changed['dialogue_actors'][0]['briefing'] = 'Changed after preview.'
    response = client.post('/api/scenes/' + run_id + '/stages', json={
        **changed, 'preview_hash': report.json()['preview_hash'], 'operation_id': uuid4().hex})
    assert response.status_code == 409
    assert len(provider.calls) == 1


@pytest.mark.parametrize('change', ['profile', 'prompt', 'branch'])
def test_character_preparation_releases_read_lock_and_rechecks_dependencies_before_insert(client, monkeypatch, change):
    from server.scenes import service
    story, run_id, provider, actors = ready(client)
    report, body = preview(client, run_id, actors)
    before = get_plan(client, run_id)
    original = service.stage_snapshot

    def racing(connection, run, request):
        result = original(connection, run, request)
        job = result['jobs'][0]
        # An independent writer must remain possible during expensive read preparation.
        from server.profiles import Profiles
        from server.prompts import Prompts, PromptUpdate
        from server.providers.config import ProfileUpdate
        database = client.app.state.database
        if change == 'profile':
            Profiles(database, None).update(job['profile']['profile_id'], ProfileUpdate(
                name='Changed profile', config=job['profile']['config'], expected_version_id=job['profile']['id']))
        elif change == 'prompt':
            Prompts(database).update('scene-dialogue', PromptUpdate(template='Changed prompt', expected_version_id=job['prompt']['id']))
        else:
            with database.connect(write=True) as writer:
                writer.execute('UPDATE branches SET revision=revision+1 WHERE id=?', (story['branch_id'],))
        return result

    monkeypatch.setattr(service, 'stage_snapshot', racing)
    response = client.post('/api/scenes/' + run_id + '/stages', json={
        **body, 'preview_hash': report.json()['preview_hash'], 'operation_id': uuid4().hex})
    assert response.status_code == 409, response.text
    assert len(provider.calls) == 1
    assert get_plan(client, run_id)['jobs'] == before['jobs']


def test_character_scene_accepts_only_after_explicit_selection_and_director_review(client):
    toggle(client, 'scene-continuity')
    story, run_id, _, actors = ready(client)
    original = client.get('/api/branches/' + story['branch_id']).json()
    job = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors)[0]
    denied = client.post('/api/scenes/' + run_id + '/accept', json={
        'expected_revision': get_plan(client, run_id)['revision'], 'operation_id': uuid4().hex, 'manual_review': True})
    assert denied.status_code == 409
    choose(client, run_id, job)
    assert client.get('/api/branches/' + story['branch_id']).json() == original
    receipt = decide(client, run_id, 'accept', {'manual_review': True})['state']['accepted']
    branch = client.get('/api/branches/' + story['branch_id']).json()
    assert branch['revision'] == original['revision'] + 1
    assert branch['messages'][-1]['id'] == receipt['node_id']
    assert branch['messages'][-1]['text'] == get_plan(client, run_id)['draft']['text']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = get_plan(client, mapping[run_id])
    assert restored['state']['accepted']['node_id'] == mapping[receipt['node_id']]


def test_dialogue_prompt_revision_preserves_custom_heads_and_story_pins(client, story):
    from server.database import one
    from server.prompts import Prompts, PromptUpdate, initialize_prompts, prompt_snapshot
    from server.role_prompts import ROLE_PROMPTS
    from server.scenes.catalog import SCENE_PROMPTS
    database = client.app.state.database
    with database.connect(write=True) as connection:
        connection.execute("UPDATE prompt_heads SET version_id='scene-dialogue-default-v1' WHERE key='scene-dialogue'")
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (
            encode({'prompt_versions': {'scene-dialogue': 'scene-dialogue-default-v1'}}), story['story_id']))
    initialize_prompts(database)
    with database.connect() as connection:
        current = prompt_snapshot(connection, 'scene-dialogue')
        assert current['template'] == ROLE_PROMPTS['scene-dialogue']
        pinned = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        assert prompt_snapshot(connection, 'scene-dialogue', pinned)['template'] == SCENE_PROMPTS['scene-dialogue']
    edited = Prompts(database).update('scene-dialogue', PromptUpdate(
        expected_version_id=current['id'], template='My custom dialogue instruction.'))
    initialize_prompts(database)
    with database.connect() as connection:
        assert prompt_snapshot(connection, 'scene-dialogue')['id'] == edited['id']
        assert one(connection, "SELECT template FROM prompt_versions WHERE id='scene-dialogue-default-v1'")['template'] == SCENE_PROMPTS['scene-dialogue']
