from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import RECIPE_TABLES
from server.database import decode, encode
from server.writing.recipe_models import RecipeStepStart
from server.writing.recipe_service import RecipeRuns
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_recipe_planning import setup
from tests.test_recipe_runs import RecipeProvider, create_run, detail, settled, start_step
from tests.test_text_edits import apply, proposal, target, undo


def imported_story(story, mapping):
    return {key: mapping[story[key]] for key in ('story_id', 'branch_id')}


def test_recipe_restores_twice_and_resumes_with_exact_frozen_inputs(client, story):
    append(client, story['branch_id'], 'The earlier room.', 0)
    _, _, body = setup(client, story)
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    start_step(client, run_id)
    settled(client, run_id)
    original = detail(client, run_id)
    next_input = client.post(f'/api/recipe-runs/{run_id}/preview-step').json()
    for _ in range(2):
        file, document = backup(client, story)
        assert document['version'] == 51 and len(document['data']['recipe_runs']) == 1
        assert 'credential_ref":null' in document['data']['recipe_runs'][0]['snapshot']
        _, mapping = restore(client, file)
        run_id, story = mapping[run_id], imported_story(story, mapping)
        value = detail(client, run_id)
        assert value['snapshot'] == original['snapshot']
        assert value['jobs'][0]['snapshot']['content'] == original['jobs'][0]['snapshot']['content']
        assert value['jobs'][0]['snapshot']['instructions'] == original['jobs'][0]['snapshot']['instructions']
        actual = client.post(f'/api/recipe-runs/{run_id}/preview-step').json()
        assert [job['content'] for job in actual['jobs']] == [job['content'] for job in next_input['jobs']]
        assert [job['instructions'] for job in actual['jobs']] == [job['instructions'] for job in next_input['jobs']]
        assert len(provider.calls) == 1
    for _ in range(2):
        start_step(client, run_id)
        value = settled(client, run_id)
    assert value['progress']['status'] == 'complete' and len(provider.calls) == 4
    receipt = apply(client, value['proposals'][0])
    undo(client, receipt)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = detail(client, mapping[run_id])
    assert restored['progress']['status'] == 'complete' and restored['proposal_id'] == mapping[value['proposal_id']]
    assert target(client, restored['target']['ref'])['text'] == body['selection']['text']
    backup(client, imported_story(story, mapping))


def test_queued_recipe_recovers_and_restores_without_provider_replay(client, story):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    service = RecipeRuns(client.app.state.database)
    preview = service.preview_step(run_id)
    created = service.start_step(run_id, RecipeStepStart(operation_id=uuid4().hex,
        expected_revision=preview['revision'], preview_hash=preview['preview_hash']))
    file, _ = backup(client, story)
    assert file['summary']['running_jobs'] == 1
    _, mapping = restore(client, file)
    assert detail(client, mapping[run_id])['jobs'][0]['status'] == 'interrupted'
    client.app.state.recipe_runner.recover()
    assert detail(client, run_id)['jobs'][0]['status'] == 'interrupted' and not provider.calls
    restored_job = mapping[created['job_ids'][0]]
    assert client.post(f'/api/recipe-jobs/{restored_job}/retry').status_code == 200
    assert settled(client, mapping[run_id])['progress']['status'] == 'complete' and len(provider.calls) == 1
    backup(client, imported_story(story, mapping))


def test_chance_is_drawn_once_and_preserved_across_restore(client, story, monkeypatch):
    _, _, body = setup(client, story, {'randomness': {'enabled': True, 'chance': 100, 'cooldown': 0}, 'steps': [{'task': 'writer'}]})
    body['beat'] = {'label': 'A completed exchange', 'completed': True}
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    chance = detail(client, run_id)['chance']
    assert chance and chance['seed'] and chance['draws']
    def no_new_seed(*args, **kwargs):
        raise AssertionError('An existing run cannot draw a new seed.')
    monkeypatch.setattr('server.writing.recipe_chance.secrets.token_hex', no_new_seed)
    start_step(client, run_id)
    value = settled(client, run_id)
    assert decode(provider.calls[0][2])['prepared_chance'] == chance['writer']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert detail(client, mapping[run_id])['chance'] == chance and len(provider.calls) == 1
    assert value['target']['text'] == target(client, body['target'])['text']


@pytest.mark.parametrize('damage', ['input', 'instructions', 'result', 'stage', 'target', 'guidance', 'binding', 'source', 'chance', 'origin', 'legacy'])
def test_recipe_archive_rejects_changed_execution_contract(client, story, damage):
    append(client, story['branch_id'], 'Earlier prose.', 0)
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    client.app.state.recipe_runner.provider = RecipeProvider()
    run_id = create_run(client, story, body)
    start_step(client, run_id)
    settled(client, run_id)
    _, document = backup(client, story)
    run, job = document['data']['recipe_runs'][0], document['data']['recipe_jobs'][0]
    snapshot, request = decode(run['snapshot']), decode(job['snapshot'])
    if damage == 'input':
        request['content'] += ' Changed.'
    elif damage == 'instructions':
        snapshot['plan'][0]['templates'][0]['instructions'] = 'Apply all changes.'
    elif damage in {'result', 'origin'}:
        damage_result(document, job, damage)
    elif damage == 'stage':
        job['stage'] = 1
    elif damage == 'target':
        value = decode(run['target'])
        value['text'] = 'Altered target.'
        run['target'] = encode(value)
    elif damage == 'guidance':
        snapshot['guidance']['resolved_recipe']['instructions'] = 'Altered recipe.'
    elif damage == 'binding':
        bindings = decode(run['bindings'])
        bindings[next(iter(bindings))] = 'missing'
        run['bindings'] = encode(bindings)
    elif damage == 'source':
        snapshot['sources']['blind'][0]['text'] = 'Other telling.'
    elif damage == 'chance':
        run['chance'] = encode({'seed': 'unexpected'})
    else:
        document['version'] = 50
    run['snapshot'], job['snapshot'] = encode(snapshot), encode(request)
    response = client.post('/api/archives/imports', json={'content': encode(document)})
    assert response.status_code == 400, response.text


def damage_result(document, job, damage):
    if damage == 'origin':
        document['data']['recipe_results'][0]['job_id'] = 'missing'
    else:
        result = decode(job['result'])
        result['replacement'] = 'Altered output.'
        job['result'] = encode(result)


def test_format_50_requires_original_groups_and_no_recipe_origins(client):
    _, document = backup(client)
    document['version'] = 50
    malformed = deepcopy(document)
    for table in RECIPE_TABLES:
        assert document['data'].pop(table) == []
    response = client.post('/api/archives/imports', json={'content': encode(document)})
    assert response.status_code == 201, response.text
    restore(client, response.json())
    assert client.post('/api/archives/imports', json={'content': encode(malformed)}).status_code == 400


def chosen_target(client, story, kind):
    from tests.test_candidate_text_edits import fixture
    from tests.test_scene_reviews import reviewable_plan
    from tests.test_scene_text_edits import source
    from tests.test_text_edit_versions import asset, field_target, prompt_target
    from tests.test_writing_resources import create
    if kind in {'character', 'canon'}:
        return field_target(client, story, asset(client, 'character' if kind == 'character' else 'lorebook'))
    if kind == 'style':
        return field_target(client, story, create(client, content={'prose': 'Spare.'}), 'prose', kind='writing-field')
    if kind in {'prompt', 'workspace-prompt'}:
        return prompt_target(client, story, scope='workspace' if kind == 'workspace-prompt' else 'story')
    if kind == 'brief':
        return target(client, {'kind': 'story-brief', 'story_id': story['story_id']})
    if kind == 'candidate':
        chosen = fixture(client, story)[3]
    elif kind == 'scene':
        chosen = source(client, reviewable_plan(client, story, dialogue=True)[0])
    else:
        first = append(client, story['branch_id'], 'The selected passage.', 0)
        append(client, story['branch_id'], 'A later passage kept intact.', 1)
        return target(client, {'kind': 'passage', **story, 'node_id': first})
    apply(client, proposal(client, chosen, 'Earlier author wording.'))
    return target(client, chosen['ref'])


@pytest.mark.parametrize('kind', ['character', 'canon', 'style', 'prompt', 'workspace-prompt', 'brief', 'candidate', 'scene', 'passage'])
def test_recipe_destinations_preserve_authority_and_source_editions_through_restores(client, story, kind):
    from server.text_edits.selection import whole_text
    chosen = chosen_target(client, story, kind)
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    body.update(target=chosen['ref'], expected_version=chosen['version'], selection=whole_text(chosen['text']), action='update')
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    # Restore before dispatch to prove target/config collection does not rely on an existing proposal.
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    original_run = run_id
    run_id, story = mapping[run_id], imported_story(story, mapping)
    start_step(client, run_id)
    value = settled(client, run_id)
    if kind == 'workspace-prompt':
        assert value['proposals'][0]['status'] == 'conflict'
    else:
        receipt = apply(client, value['proposals'][0])
        assert receipt['after_target']['text'] == '  She waited. 🕯\n'
        inverse = undo(client, receipt)
        assert inverse['receipt']['after_target']['text'] == chosen['text']
    assert target(client, chosen['ref'])['text'] == chosen['text']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert detail(client, mapping[run_id])['snapshot'] == detail(client, original_run)['snapshot']
    backup(client, imported_story(story, mapping))


@pytest.mark.parametrize('field,value', [('completed', False), ('finish_reason', 'length'), ('output_limit_uncertain', True)])
def test_recipe_archive_requires_successful_completion_evidence(client, story, field, value):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    client.app.state.recipe_runner.provider = RecipeProvider()
    run_id = create_run(client, story, body)
    start_step(client, run_id)
    settled(client, run_id)
    _, document = backup(client, story)
    job = document['data']['recipe_jobs'][0]
    usage = decode(job['usage'])
    usage['completion'][field] = value
    job['usage'] = encode(usage)
    response = client.post('/api/archives/imports', json={'content': encode(document)})
    assert response.status_code == 400, response.text


def test_ready_run_keeps_old_editions_and_excludes_private_discussion(client, story):
    from server.prompts import Prompts, PromptUpdate
    from tests.test_sidebar import CollaboratorProvider, ask, settle, thread
    from tests.test_writing_resources import create
    style = create(client, content={'prose': 'Use short clauses.', 'examples': [{'label': 'Example', 'text': 'The lamp dimmed.'}]})
    _, recipe, body = setup(client, story, {'style': style['id'], 'steps': [{'task': 'writer'}, {'task': 'review', 'lenses': ['dialogue']}]})
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    original = client.post(f'/api/recipe-runs/{run_id}/preview-step').json()['jobs'][0]
    prompt = original['prompt']
    Prompts(client.app.state.database).update(prompt['key'], PromptUpdate(expected_version_id=prompt['id'], template='LATER_PROMPT_ONLY'))
    changed = client.post(f"/api/writing-resources/{recipe['asset_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': recipe['id'], 'kind': 'recipe', 'name': 'Later recipe',
        'content': {'instructions': 'LATER_RECIPE_ONLY', 'steps': [{'task': 'writer'}]}})
    assert changed.status_code == 201, changed.text
    discussion = thread(client, story)
    client.app.state.side_runner.provider = CollaboratorProvider()
    ask(client, discussion, story)
    settle(client)
    file, document = backup(client, story)
    assert document['data']['side_threads'] == [] and document['data']['side_turns'] == []
    assert recipe['id'] in {row['id'] for row in document['data']['writing_versions']}
    assert prompt['id'] in {row['id'] for row in document['data']['prompt_versions']}
    _, mapping = restore(client, file)
    run_id = mapping[run_id]
    prepared, _ = start_step(client, run_id)
    assert prepared['jobs'][0]['instructions'] == original['instructions'] and prepared['jobs'][0]['content'] == original['content']
    settled(client, run_id)
    start_step(client, run_id)
    value = settled(client, run_id)
    assert value['progress']['status'] == 'complete' and len(provider.calls) == 2
    assert value['proposals'][0]['replacement'] == '  She waited. 🕯\n'
    backup(client, imported_story(story, mapping))


def test_skipped_readers_and_long_story_budget_evidence_restore(client):
    from tests.test_branch_tools import branch
    from tests.test_memory import small_profile
    story = client.post('/api/stories', json={'title': 'Long recipe', 'settings': {'memory': {'mode': 'long'}, 'disabled_prompts': []}}).json()
    _, _, body = setup(client, story, {'disabled_tasks': ['review-blind', 'review-informed'],
        'steps': [{'task': 'writer'}, {'task': 'review'}, {'task': 'revision'}]})
    for index in range(6):
        append(client, story['branch_id'], f'Earlier room {index}. ' * 240, index)
    model = small_profile(client, 'Bounded recipe writer', 18000)
    body.update(expected_revision=branch(client, story['branch_id'])['revision'], profiles={'writer': model['profile_id']})
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    for _ in range(2):
        start_step(client, run_id)
        value = settled(client, run_id)
    assert value['progress']['status'] == 'complete' and value['snapshot']['plan'][1]['skipped']
    assert len(value['jobs']) == 2 and len(provider.calls) == 2
    original = value['jobs'][0]['snapshot']
    assert original['source_memory']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = detail(client, mapping[run_id])['jobs'][0]['snapshot']
    assert restored['content'] == original['content'] and restored['source_memory'] == original['source_memory']
    backup(client, imported_story(story, mapping))
