import json
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION, RECIPE_TABLES, STYLE_ANALYSIS_TABLES
from server.database import decode, encode
from tests.test_archives import backup, restore
from tests.test_memory import small_profile
from tests.test_profiles import make_profile
from tests.test_scene_character_writers import ready
from tests.test_scene_drafting import approved_plan
from tests.test_scene_patches import ready_patch
from tests.test_scenes import choose, finish_plan, get_plan, run_stage
from tests.test_writing_resources import create, pins


def stage_preview(client, run_id, key, **extra):
    body = {'expected_revision': get_plan(client, run_id)['revision'], 'key': key, **extra}
    return client.post(f'/api/scenes/{run_id}/preview', json=body), body


@pytest.mark.parametrize('mode', ['full', 'long'])
@pytest.mark.parametrize('key', ['scene-draft', 'scene-dialogue', 'scene-patch', 'scene-dialogue-patch'])
def test_styled_scene_stages_preview_exact_inputs_and_restore_twice(client, key, mode):
    story = client.post('/api/stories', json={'title': 'Styled scene', 'settings': {'memory': {'mode': mode}, 'disabled_prompts': []}}).json()
    style = create(client, content={'prose': 'Use concrete verbs.', 'examples': [{'label': 'Example only', 'text': 'The kettle cooled.'}]})
    if 'patch' in key:
        run_id, _ = ready_patch(client, story, dialogue=True)
        if key == 'scene-dialogue-patch':
            choose(client, run_id, run_stage(client, run_id, 'scene-patch')[0])
    else:
        run_id, _ = approved_plan(client, story, dialogue=True)
        if key == 'scene-dialogue':
            choose(client, run_id, run_stage(client, run_id, 'scene-draft')[0])
    recipe_profile = make_profile(client, 'Recipe stage model')
    task = 'revision' if 'patch' in key else 'writer'
    recipe = create(client, 'recipe', {'purpose': 'revise' if task == 'revision' else 'draft', 'style': style['id'],
                    'instructions': 'Preserve {{detail}}.', 'variables': [{'name': 'detail', 'label': 'Detail'}],
                    'steps': [{'task': task, 'profile_id': recipe_profile['profile_id'], 'instructions': 'Keep the dialogue grounded.'}]})
    writing = {'recipe': recipe['id'], 'variables': {'detail': 'the unopened letter'}}
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    response, _ = stage_preview(client, run_id, key, writing=writing)
    assert response.status_code == 200, response.text
    preview = response.json()['jobs'][0]
    assert preview['profile_name'] == recipe_profile['name'] and preview['cost'] is None
    assert preview['writing']['style'] == {'name': style['name'], 'number': style['number']}
    explicit_profile = make_profile(client, 'Explicit stage override')
    explicit, _ = stage_preview(client, run_id, key, writing=writing, profile_ids=[explicit_profile['profile_id']])
    assert explicit.json()['jobs'][0]['profile_name'] == explicit_profile['name']
    job = run_stage(client, run_id, key, writing=writing)[0]
    assert job['status'] == 'done', job['error']
    assert job['snapshot']['content'] == preview['content']
    content = decode(preview['content'])
    assert content['writing_guidance']['resolved_recipe']['instructions'] == 'Preserve the unopened letter.'
    assert content['writing_guidance']['style']['content']['examples'][0]['text'] == 'The kettle cooled.'
    assert content['writing_task']['task'] == task
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    restored = get_plan(client, mapping[run_id])
    assert next(item for item in restored['jobs'] if item['id'] == mapping[job['id']])['snapshot']['content'] == preview['content']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


def test_story_style_applies_to_prose_but_not_factual_stages_and_explicit_none_wins(client, story):
    style = create(client)
    pins(client, story, style['id'])
    run_id, provider = approved_plan(client, story)
    assert all('writing_guidance' not in decode(call[2]) for call in provider.calls)
    draft = run_stage(client, run_id, 'scene-draft')[0]
    assert draft['snapshot']['writing_guidance']['style']['id'] == style['id']
    choose(client, run_id, draft)
    coverage = run_stage(client, run_id, 'scene-coverage')[0]
    assert 'writing_guidance' not in coverage['snapshot'] and 'writing_task' not in decode(coverage['snapshot']['content'])
    refused, _ = stage_preview(client, run_id, 'scene-coverage', writing={'style': style['id']})
    assert refused.status_code == 409
    plain = run_stage(client, run_id, 'scene-draft', writing={'style': 'none', 'recipe': 'none'})[0]
    assert 'writing_guidance' not in plain['snapshot']


def test_changed_style_preview_rejects_without_record_and_retry_keeps_original_inputs(client, story):
    first, second = create(client), create(client, name='Later style', content={'rhythm': 'Longer sentences.'})
    pins(client, story, first['id'])
    run_id, provider = approved_plan(client, story)
    preview, body = stage_preview(client, run_id, 'scene-draft')
    before = get_plan(client, run_id)
    pins(client, story, second['id'])
    stale = client.post(f'/api/scenes/{run_id}/stages', json={**body, 'operation_id': uuid4().hex, 'preview_hash': preview.json()['preview_hash']})
    assert stale.status_code == 409
    after = get_plan(client, run_id)
    assert after['jobs'] == before['jobs'] and after['decisions'] == before['decisions'] and after['stale']
    run_id, provider = approved_plan(client, story)
    provider.corrupt = lambda output: output.update(extra='Invalid structured output')
    failed = run_stage(client, run_id, 'scene-draft')[0]
    assert failed['status'] == 'error'
    inputs = provider.calls[-1][1:]
    pins(client, story, first['id'])
    provider.corrupt = None
    assert client.post(f"/api/scene-jobs/{failed['id']}/retry", json={}).status_code == 200
    done = next(job for job in finish_plan(client, run_id)['jobs'] if job['id'] == failed['id'])
    assert done['status'] == 'done' and provider.calls[-1][1:] == inputs


def test_styled_character_dialogue_keeps_complete_evidence_and_private_scope(client):
    story, run_id, provider, actors = ready(client)
    style = create(client, content={'dialogue': 'Understated, specific replies.', 'examples': [{'label': 'Style only', 'text': 'I kept the key.'}]})
    report, body = stage_preview(client, run_id, 'scene-dialogue', dialogue_actors=actors, writing={'style': style['id']})
    assert report.status_code == 200, report.text
    packets = report.json()['jobs'][0]['dialogue_actors']
    assert all(decode(item['content'])['writing_guidance']['style']['id'] == style['id'] for item in packets)
    assert 'NARRATOR_SECRET' not in encode(packets) and 'SLOT_SECRET' not in encode(packets)
    assert 'VISIBLE_SECOND' not in packets[0]['content'] and 'SECOND_ONLY' not in packets[0]['content']
    job = run_stage(client, run_id, 'scene-dialogue', dialogue_actors=actors, writing=body['writing'])[0]
    assert job['status'] == 'done', job['error']
    assert [call[2] for call in provider.calls[-2:]] == [item['content'] for item in packets]
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


def test_style_cannot_displace_character_evidence_to_fit_budget(client):
    _, run_id, provider, actors = ready(client)
    style = create(client, content={'prose': 'x ' * 6000})
    profile = small_profile(client, 'Bounded character writer', 4096)
    before = len(provider.calls), get_plan(client, run_id)
    response, _ = stage_preview(client, run_id, 'scene-dialogue', dialogue_actors=actors, profile_ids=[profile['profile_id']], writing={'style': style['id']})
    assert response.status_code == 409 and 'No evidence was dropped' in response.text
    assert (len(provider.calls), get_plan(client, run_id)) == before


def test_consolidated_scene_styles_only_prose_calls_and_preserves_acceptance(client, story):
    from tests.test_consolidated_scene import drafted_scene, scene_readers, selected
    from tests.test_scenes import decide
    style = create(client)
    pins(client, story, style['id'])
    scene_id, provider = drafted_scene(client, story)
    review = scene_readers(client, story, scene_id)
    selected(client, scene_id, 'scene-triage', review_job_ids=[job['id'] for job in review['jobs']])
    decide(client, scene_id, 'approve-revision', {'package': 'B'})
    selected(client, scene_id, 'scene-patch')
    selected(client, scene_id, 'scene-continuity')
    assert len(provider.calls) == 9
    for _, _, raw in provider.calls:
        content = decode(raw)
        prose = content.get('stage') in {'scene-draft', 'scene-dialogue', 'scene-patch'}
        assert bool(content.get('writing_guidance')) == prose
    decide(client, scene_id, 'accept', {'selected_ids': [], 'include_summary': True})
    assert len(provider.calls) == 9 and get_plan(client, scene_id)['state']['accepted']
    file, _ = backup(client, story)
    restore(client, file)


def test_recipe_cannot_enable_a_workspace_disabled_scene_writer(client, story):
    from tests.test_agent_switches import toggle
    run_id, provider = approved_plan(client, story)
    recipe = create(client, 'recipe', {'steps': [{'task': 'writer'}]})
    before = len(provider.calls)
    toggle(client, 'scene-draft')
    response, _ = stage_preview(client, run_id, 'scene-draft', writing={'recipe': recipe['id']})
    assert response.status_code == 409 and len(provider.calls) == before


def test_stage_rechecks_writing_dependencies_after_read_preparation(client, story, monkeypatch):
    from server.agent_switches import set_agent, switch_state
    from server.scenes import service
    run_id, provider = approved_plan(client, story)
    style = create(client)
    preview, body = stage_preview(client, run_id, 'scene-draft', writing={'style': style['id']})
    before, calls = get_plan(client, run_id), len(provider.calls)
    original = service.stage_snapshot

    def racing(connection, run, request):
        prepared = original(connection, run, request)
        # A workspace switch changes the resolved disable ceiling without changing
        # the Story revision, so the writing dependency check must catch it.
        with client.app.state.database.connect(write=True) as writer:
            set_agent(writer, 'review-blind', False, switch_state(writer)['revision'])
        return prepared

    monkeypatch.setattr(service, 'stage_snapshot', racing)
    response = client.post(f'/api/scenes/{run_id}/stages', json={
        **body, 'preview_hash': preview.json()['preview_hash'], 'operation_id': uuid4().hex})
    assert response.status_code == 409 and 'Writing preferences changed' in response.text
    assert get_plan(client, run_id) == before and len(provider.calls) == calls


def test_format_48_scene_restores_unchanged_without_new_writing_fields(client, story):
    run_id, _ = approved_plan(client, story)
    job = run_stage(client, run_id, 'scene-draft')[0]
    _, document = backup(client, story)
    document['version'] = 48
    for table in STYLE_ANALYSIS_TABLES + RECIPE_TABLES:
        assert document['data'].pop(table) == []
    imported = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert imported.status_code == 201, imported.text
    _, mapping = restore(client, imported.json())
    restored = get_plan(client, mapping[run_id])
    assert next(item for item in restored['jobs'] if item['id'] == mapping[job['id']])['snapshot']['content'] == job['snapshot']['content']


@pytest.mark.parametrize('damage', ['task', 'content', 'legacy', 'actor'])
def test_styled_scene_archive_rejects_changed_task_guidance_or_legacy_claim(client, story, damage):
    if damage == 'actor':
        story, run_id, _, actors = ready(client)
        key, extra = 'scene-dialogue', {'dialogue_actors': actors}
    else:
        run_id, _ = approved_plan(client, story)
        key, extra = 'scene-draft', {}
    style = create(client)
    job = run_stage(client, run_id, key, writing={'style': style['id']}, **extra)[0]
    _, document = backup(client, story)
    row = next(row for row in document['data']['scene_jobs'] if row['id'] == job['id'])
    snapshot = decode(row['snapshot'])
    if damage == 'legacy':
        document['version'] = 48
    elif damage == 'actor':
        snapshot['dialogue_actors'][0]['writing_guidance'] = None
    else:
        content = decode(snapshot['content'])
        if damage == 'task':
            content['writing_task']['task'] = 'review'
        else:
            content['writing_guidance']['style']['content']['prose'] = 'Tampered guidance.'
        snapshot['content'] = encode(content)
    row['snapshot'] = encode(snapshot)
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400, response.text
