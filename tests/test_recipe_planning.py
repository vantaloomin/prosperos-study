from copy import deepcopy
from uuid import uuid4

import pytest

from server.agent_switches import set_agents, switch_state
from server.database import decode, encode, one
from server.errors import DomainError
from server.text_edits.selection import whole_text
from server.workflow.runner import parse_review
from server.writing.recipe_chance import resolve_chance
from server.writing.recipe_context import compile_job
from server.writing.recipe_models import RecipeRunPreview
from server.writing.recipe_output import parse_recipe_output
from server.writing.recipe_plan import prepare_recipe
from tests.test_branch_tools import branch, fork
from tests.test_context_inspector import database_dump
from tests.test_history import append
from tests.test_memory import small_profile
from tests.test_profiles import make_profile
from tests.test_text_edits import save_document, target
from tests.test_writing_resources import create, pins


def setup(client, story, content=None, text='  The kettle cooled.\nShe waited. 🕯\n'):
    model = make_profile(client, 'Recipe model', primary=True)
    recipe = create(client, 'recipe', content or {'instructions': 'Preserve the pause.', 'steps': [
        {'task': 'writer'}, {'task': 'review', 'lenses': ['dialogue', 'continuity']}, {'task': 'revision'}]})
    source = target(client, {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': 'composer'})
    source = save_document(client, source, text)
    return model, recipe, {'expected_revision': branch(client, story['branch_id'])['revision'], 'target': source['ref'],
                          'expected_version': source['version'], 'selection': whole_text(text), 'writing': {'recipe': recipe['id']}}


def preview(client, story, body, status=200):
    response = client.post(f"/api/branches/{story['branch_id']}/writing-recipes/preview", json=body)
    assert response.status_code == status, response.text
    return response.json()


def frozen(client, story, body):
    with client.app.state.database.connect() as connection:
        return prepare_recipe(connection, story['branch_id'], RecipeRunPreview.model_validate(body))


def test_complete_recipe_preview_is_read_only_and_marks_dependent_inputs(client, story):
    _, _, body = setup(client, story)
    before = database_dump(client)
    result = preview(client, story, body)
    assert database_dump(client) == before
    assert result['maximum_calls'] == 4 and result['provider_cost'] is None
    assert [step['task'] for step in result['plan']] == ['writer', 'review', 'revision']
    first = result['plan'][0]['requests'][0]
    assert first['exact'] and decode(first['content'])['sources'][0]['text'] == body['selection']['text']
    assert all(not request['exact'] and request['content'] is None and request['estimated_input_tokens'] is None
               for step in result['plan'][1:] for request in step['requests'])
    assert 'credential_ref' not in encode(result)
    assert preview(client, story, body)['preview_hash'] == result['preview_hash']


def test_recipes_compile_isolated_readers_and_styled_revision_from_frozen_inputs(client, story):
    _, recipe, body = setup(client, story)
    style = create(client, content={'prose': 'Short concrete clauses.', 'examples': [{'label': 'Example only', 'text': 'STYLE_ONLY_SECRET'}]})
    pins(client, story, style['id'])
    body['expected_revision'] = branch(client, story['branch_id'])['revision']
    plan = frozen(client, story, body)
    # Later Library changes and Story pins cannot affect the compiled run.
    pins(client, story, 'none', 'none')
    newer = client.post(f"/api/writing-resources/{recipe['asset_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': recipe['id'], 'kind': 'recipe', 'name': 'Changed recipe',
        'content': {'instructions': 'NEW_INSTRUCTIONS', 'steps': [{'task': 'writer'}]}})
    assert newer.status_code == 201
    writer = compile_job(plan, plan['plan'][0]['templates'][0], None)
    assert 'STYLE_ONLY_SECRET' in writer['content'] and 'NEW_INSTRUCTIONS' not in writer['content']
    reviews = [compile_job(plan, template, 'The revised draft.') for template in plan['plan'][1]['templates']]
    assert all('STYLE_ONLY_SECRET' not in job['content'] and 'review_suggestions' not in job['content'] for job in reviews)
    assert all(decode(job['content'])['sources'][0]['text'] == 'The revised draft.' for job in reviews)
    report = {'summary': 'Keep the pause.', 'findings': []}
    assert parse_review(encode(report), reviews[0]['content'])['summary'] == report['summary']
    revision = compile_job(plan, plan['plan'][2]['templates'][0], 'The revised draft.', [report])
    assert decode(revision['content'])['review_suggestions'] == [report]
    assert 'STYLE_ONLY_SECRET' in revision['content'] and 'NEW_INSTRUCTIONS' not in revision['content']
    assert compile_job(plan, plan['plan'][2]['templates'][0], 'The revised draft.', [report]) == revision


def test_role_scope_omits_future_sibling_and_privileged_blind_sources(client, story):
    first = append(client, story['branch_id'], 'EARLY_PERMITTED_TEXT', 0)
    selected = append(client, story['branch_id'], 'Selected prose.', 1)
    append(client, story['branch_id'], 'FUTURE_TEXT_EXCLUDED', 2)
    sibling = fork(client, story['branch_id'], first, name='Private sibling')
    append(client, sibling, 'SIBLING_TEXT_EXCLUDED', branch(client, sibling)['revision'])
    _, _, body = setup(client, story, {'purpose': 'review', 'steps': [{'task': 'review', 'lenses': ['dialogue', 'rules']}]})
    chosen = target(client, {'kind': 'passage', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'node_id': selected})
    body.update(target=chosen['ref'], expected_version=chosen['version'], selection=whole_text(chosen['text']))
    result = preview(client, story, body)
    jobs = result['plan'][0]['requests']
    assert all('FUTURE_TEXT_EXCLUDED' not in job['content'] and 'SIBLING_TEXT_EXCLUDED' not in job['content'] for job in jobs)
    blind, informed = [decode(job['content']) for job in jobs]
    assert all(source['kind'] in {'draft', 'previous'} for source in blind['sources'])
    assert 'author_memory' not in blind and 'approved_beats' not in blind
    assert any(source['id'] == 'story:constraints' for source in informed['sources'])


def test_explicit_models_and_switches_override_defaults_but_not_workspace_ceiling(client, story):
    _, recipe, body = setup(client, story)
    recipe_model = make_profile(client, 'Recipe reviewer')
    explicit = make_profile(client, 'Explicit reviewer')
    with client.app.state.database.connect(write=True) as connection:
        saved = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        settings = {**decode(saved['settings']), 'disabled_prompts': ['review-blind'],
                    'step_profiles': {'review-informed': recipe_model['profile_id']}}
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
    body.update(profiles={'review': explicit['profile_id']}, task_switches={'review-blind': True})
    result = preview(client, story, body)
    assert len(result['plan'][1]['requests']) == 2
    assert all(job['profile']['profile_id'] == explicit['profile_id'] and job['profile_source'] == 'request' for job in result['plan'][1]['requests'])
    with client.app.state.database.connect(write=True) as connection:
        set_agents(connection, ['review-blind', 'review-informed'], False, switch_state(connection)['revision'])
    result = preview(client, story, body)
    assert result['plan'][1]['skipped'] and not result['plan'][1]['requests'] and result['maximum_calls'] == 2
    assert 'review-blind' in result['switches']['workspace_disabled']
    assert recipe['id'] == result['writing']['recipe']['id']


@pytest.mark.parametrize('content,extra', [
    ({'steps': [{'task': 'review'}, {'task': 'writer'}]}, {}),
    ({'purpose': 'review', 'steps': [{'task': 'revision'}]}, {}),
    ({'purpose': 'revise', 'steps': [{'task': 'writer'}]}, {}),
    ({'steps': [{'task': 'writer'}]}, {'profiles': {'review': 'missing'}}),
    ({'steps': [{'task': 'writer'}]}, {'task_switches': {'made-up-task': True}}),
    ({'purpose': 'review', 'steps': [{'task': 'review'}]}, {'review_lenses': ['dialogue', 'dialogue']}),
    ({'purpose': 'review', 'steps': [{'task': 'review', 'lenses': ['coverage']}]}, {}),
])
def test_complete_configuration_is_validated_before_work(client, story, content, extra):
    _, _, body = setup(client, story, content)
    body.update(extra)
    before = database_dump(client)
    response = client.post(f"/api/branches/{story['branch_id']}/writing-recipes/preview", json=body)
    assert response.status_code in {400, 409}, response.text
    assert database_dump(client) == before


def test_chance_preview_freezes_tables_without_draws_or_state_changes(client, story, monkeypatch):
    _, _, body = setup(client, story, {'randomness': {'enabled': True, 'chance': 23, 'cooldown': 0}, 'steps': [{'task': 'writer'}]})
    preview(client, story, body, 409)
    body['beat'] = {'label': 'A completed exchange', 'completed': True}
    def reject_draw(*args, **kwargs):
        raise AssertionError('A preview must never roll.')
    monkeypatch.setattr('server.mechanics.randomness.Draws.die', reject_draw)
    before = database_dump(client)
    result = preview(client, story, body)
    assert database_dump(client) == before
    assert result['chance']['settings']['chance'] == 23 and result['chance']['source'] == 'recipe'
    assert result['chance']['tables'] and result['chance']['settings']['table_versions']
    assert result['plan'][0]['requests'][0]['awaiting'] == 'Recorded chance result'
    assert not result['plan'][0]['requests'][0]['exact']
    invalid = deepcopy(body)
    invalid['beat']['extras'] = ['missing-table']
    preview(client, story, invalid, 400)
    body.update(randomness={'enabled': False}, beat=None)
    assert preview(client, story, body)['chance']['source'] == 'request'


@pytest.mark.parametrize('mode', ['full', 'long'])
def test_required_recipe_style_and_working_material_never_disappear_to_fit(client, mode):
    story = client.post('/api/stories', json={'title': 'Budget', 'settings': {'memory': {'mode': mode}, 'disabled_prompts': []}}).json()
    _, _, body = setup(client, story)
    small_profile(client, limit=4096)
    style = create(client, content={'examples': [{'label': 'Required style sample', 'text': 'EXACT_REQUIRED_SAMPLE ' * 900}]})
    body['writing']['style'] = style['id']
    result = preview(client, story, body, 409)
    assert any(word in result['detail'] for word in ('allowance', 'context', 'exceed'))


def test_later_stage_budget_is_checked_with_the_actual_upstream_result(client, story):
    _, _, body = setup(client, story)
    plan = frozen(client, story, body)
    template = plan['plan'][1]['templates'][0]
    with pytest.raises(DomainError, match='complete working text'):
        compile_job(plan, template, 'A required new draft. ' * 6000)
    preview_job = compile_job(plan, template, 'Small exact draft.')
    assert decode(preview_job['content'])['sources'][0]['text'] == 'Small exact draft.'


def test_target_changes_and_foreign_branch_are_rejected_before_preparing(client, story):
    _, _, body = setup(client, story)
    wrong = deepcopy(body)
    wrong['selection']['text'] = 'changed'
    preview(client, story, wrong, 409)
    source = target(client, body['target'])
    save_document(client, source, 'A later author edit.')
    preview(client, story, body, 409)
    other = client.post('/api/stories', json={'title': 'Other Story'}).json()
    wrong['target']['story_id'] = other['story_id']
    preview(client, story, wrong, 409)


def test_recipe_routes_and_variables_are_resolved_before_compiling_specialists(client, story):
    routed = make_profile(client, 'Recipe-specific reader')
    _, _, body = setup(client, story, {'instructions': 'Keep {{focus}} visible.',
        'variables': [{'name': 'focus', 'label': 'Focus'}], 'steps': [
            {'task': 'writer'}, {'task': 'review', 'profile_id': routed['profile_id'], 'lenses': ['dialogue']}, {'task': 'revision'}]})
    body['writing']['variables'] = {'focus': '{{not_a_second_template}}'}
    plan = frozen(client, story, body)
    reader = compile_job(plan, plan['plan'][1]['templates'][0], 'Exact new draft.')
    assert reader['profile']['profile_id'] == routed['profile_id'] and reader['profile_source'] == 'recipe'
    assert decode(reader['content'])['recipe_task']['instructions'] == 'Keep {{not_a_second_template}} visible.'
    body['writing']['variables'] = {}
    preview(client, story, body, 400)


def test_chance_uses_existing_engine_and_is_frozen_without_committing_story_state(client, story):
    _, _, body = setup(client, story, {'randomness': {'enabled': True, 'chance': 100, 'cooldown': 0}, 'steps': [{'task': 'writer'}]})
    body['beat'] = {'label': 'An eligible exchange', 'completed': True}
    plan = frozen(client, story, body)
    before = database_dump(client)
    chance = resolve_chance(plan['chance'], seed='recipe-test-seed')
    assert chance['draws'] and chance['before'] == plan['chance']['before']
    assert resolve_chance(plan['chance'], seed=chance['seed']) == chance
    job = compile_job(plan, plan['plan'][0]['templates'][0], None, chance=chance)
    assert decode(job['content'])['prepared_chance'] == chance['writer']
    assert 'seed' not in decode(job['content'])['prepared_chance']
    assert database_dump(client) == before


@pytest.mark.parametrize('change', ['foreign-source', 'repeated-source', 'extra-authority', 'malformed'])
def test_recipe_writer_output_cannot_expand_the_destination_or_source_scope(client, story, change):
    _, _, body = setup(client, story)
    plan = frozen(client, story, body)
    job = compile_job(plan, plan['plan'][0]['templates'][0], None)
    output = {'replacement': '  Kept exact. 🕯\n', 'explanation': 'A wording proposal.', 'source_ids': ['recipe:draft']}
    assert parse_recipe_output(encode(output), job) == output
    if change == 'foreign-source':
        output['source_ids'] = ['sibling:private']
    elif change == 'repeated-source':
        output['source_ids'] *= 2
    elif change == 'extra-authority':
        output['authority'] = 'apply'
    with pytest.raises(DomainError):
        parse_recipe_output('not JSON' if change == 'malformed' else encode(output), job)


def test_scene_recipe_coverage_uses_the_complete_working_scene_without_accepting_it(client, story):
    from tests.test_scene_drafting import LINE, PROSE, approved_plan
    from tests.test_scene_text_edits import source
    from tests.test_scenes import choose, run_stage

    scene_id, _ = approved_plan(client, story, dialogue=True)
    choose(client, scene_id, run_stage(client, scene_id, 'scene-draft')[0])
    choose(client, scene_id, run_stage(client, scene_id, 'scene-dialogue')[0])
    chosen = source(client, scene_id)
    _, _, body = setup(client, story, {'purpose': 'revise', 'steps': [
        {'task': 'review', 'lenses': ['coverage', 'dialogue']}, {'task': 'revision'}]})
    body.update(target=chosen['ref'], expected_version=chosen['version'], selection=whole_text(chosen['text']))
    before = database_dump(client)
    plan = frozen(client, story, body)
    jobs = [compile_job(plan, template, None) for template in plan['plan'][0]['templates']]
    blind, informed = [decode(job['content']) for job in jobs]
    assert 'approved_beats' not in blind and informed['approved_beats']['beats']
    assert next(item['text'] for item in informed['sources'] if item['kind'] == 'draft') == PROSE + '\n\n' + LINE
    renewed = compile_job(plan, plan['plan'][0]['templates'][1], 'New block wording.')
    assert next(item['text'] for item in decode(renewed['content'])['sources'] if item['kind'] == 'draft') == 'New block wording.\n\n' + LINE
    assert database_dump(client) == before


def test_candidate_recipe_retains_its_original_story_boundary(client, story):
    from tests.test_generations import DraftProvider, finished, generate

    _, _, body = setup(client, story, {'purpose': 'revise', 'steps': [{'task': 'revision'}]})
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    first = append(client, story['branch_id'], 'Before the unaccepted draft.', 0)
    generation = finished(client, generate(client, story, revision=1)['id'])
    append(client, story['branch_id'], 'LATER_STORY_TEXT', 1)
    chosen = target(client, {'kind': 'candidate', 'story_id': story['story_id'], 'branch_id': story['branch_id'],
                             'candidate_id': generation['candidates'][0]['id']})
    body.update(target=chosen['ref'], expected_version=chosen['version'], selection=whole_text(chosen['text']), expected_revision=2)
    plan = frozen(client, story, body)
    job = compile_job(plan, plan['plan'][0]['templates'][0], None)
    assert plan['sources']['boundary']['head_id'] == first
    assert 'Before the unaccepted draft.' in job['content'] and 'LATER_STORY_TEXT' not in job['content']
    assert len(provider.calls) == 1


def test_retained_reader_routing_and_disabled_lenses_keep_existing_contracts(client, story):
    _, _, body = setup(client, story, {'purpose': 'review', 'steps': [{'task': 'review', 'lenses': ['dialogue', 'pacing', 'rules']}]})
    routed = make_profile(client, 'Deliberate dialogue reader')
    with client.app.state.database.connect(write=True) as connection:
        row = one(connection, 'SELECT settings FROM stories WHERE id=?', (story['story_id'],))
        settings = {**decode(row['settings']), 'step_profiles': {'review-dialogue': routed['profile_id']},
                    'disabled_prompts': ['review-pacing']}
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
    result = preview(client, story, body)
    jobs = result['plan'][0]['requests']
    assert len(jobs) == 2
    assert jobs[0]['step'] == 'review-dialogue' and jobs[0]['profile']['profile_id'] == routed['profile_id']
    assert 'reader_contract' not in decode(jobs[0]['content'])
    assert jobs[1]['step'] == 'review-informed' and [lens['key'] for lens in decode(jobs[1]['content'])['lenses']] == ['rules']


def test_long_story_recipe_preserves_required_targets_and_discloses_omitted_history(client):
    story = client.post('/api/stories', json={'title': 'Long recipe', 'settings': {'memory': {'mode': 'long'}, 'disabled_prompts': []}}).json()
    _, _, body = setup(client, story, {'purpose': 'revise', 'steps': [{'task': 'revision'}]})
    for index in range(12):
        append(client, story['branch_id'], f'Accepted passage {index}. ' + 'The market was quiet. ' * 120, index)
    small_profile(client, limit=4096)
    body['expected_revision'] = 12
    plan = frozen(client, story, body)
    job = compile_job(plan, plan['plan'][0]['templates'][0], None)
    assert job['source_memory']['mode'] == 'long' and job['source_memory']['selective']
    assert not job['source_memory']['coverage']['complete_history']
    assert decode(job['content'])['sources'][0]['text'] == body['selection']['text']
    assert job['estimated_input_tokens'] + job['overhead_margin'] <= job['input_allowance']


def test_revision_inherits_chance_as_inapplicable_and_refuses_an_explicit_new_event(client, story):
    _, _, body = setup(client, story, {'purpose': 'revise', 'steps': [{'task': 'revision'}]})
    with client.app.state.database.connect(write=True) as connection:
        row = one(connection, 'SELECT settings FROM stories WHERE id=?', (story['story_id'],))
        settings = {**decode(row['settings']), 'randomness': {'enabled': True, 'automatic_assessment': True}}
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
    report = preview(client, story, body)
    assert not report['chance']['applicable'] and not report['chance']['automatic_assessment_applicable']
    assert report['chance']['settings']['automatic_assessment']
    assert report['plan'][0]['requests'][0]['exact']
    body['randomness'] = {'enabled': True}
    preview(client, story, body, 409)
    body['randomness'] = {'enabled': False}
    assert preview(client, story, body)['chance']['source'] == 'request'
