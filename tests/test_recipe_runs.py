import asyncio
import time
from copy import deepcopy
from uuid import uuid4

import pytest

from server.agent_switches import set_agents, switch_state
from server.database import decode, encode
from server.providers.events import ProviderEvent
from tests.test_context_inspector import database_dump
from tests.test_recipe_planning import preview, setup
from tests.test_text_edits import apply, save_document, target, undo


class RecipeProvider:
    def __init__(self, mode='valid'):
        self.mode, self.calls = mode, []

    async def generate(self, profile, prompt, content):
        self.calls.append((deepcopy(profile), prompt, content))
        task = decode(content)['recipe_task']['task']
        value = ({'summary': 'Keep the pause.', 'findings': []} if task == 'review' else
                 {'replacement': '  She waited. 🕯\n' if task == 'writer' else '  She waited, listening. 🕯\n',
                  'explanation': 'Preserved the pause.', 'source_ids': ['recipe:draft']})
        if self.mode == 'authority':
            value['apply'] = True
        if self.mode == 'foreign':
            value['source_ids'] = ['secret:other-story']
        yield ProviderEvent(text='broken JSON' if self.mode == 'invalid' else encode(value))
        if self.mode == 'wait':
            await asyncio.sleep(60)
        if self.mode != 'partial':
            yield ProviderEvent(done=True, usage={'finish_reason': 'length'} if self.mode == 'length' else
                                {'output_limit_uncertain': True} if self.mode == 'uncertain' else {})


def create_run(client, story, body):
    prepared = preview(client, story, body)
    request = {**body, 'operation_id': uuid4().hex, 'preview_hash': prepared['preview_hash']}
    endpoint = f"/api/branches/{story['branch_id']}/recipe-runs"
    response = client.post(endpoint, json=request)
    assert response.status_code == 201, response.text
    assert client.post(endpoint, json=request).json() == response.json()
    assert client.get('/api/recipe-runs/operations/' + request['operation_id']).json() == response.json()
    return response.json()['id']


def detail(client, run_id):
    response = client.get(f'/api/recipe-runs/{run_id}')
    assert response.status_code == 200, response.text
    return response.json()


def start_step(client, run_id):
    before = database_dump(client)
    response = client.post(f'/api/recipe-runs/{run_id}/preview-step')
    assert response.status_code == 200, response.text
    prepared = response.json()
    assert database_dump(client) == before
    request = {'operation_id': uuid4().hex, 'expected_revision': prepared['revision'], 'preview_hash': prepared['preview_hash']}
    endpoint = f'/api/recipe-runs/{run_id}/steps'
    response = client.post(endpoint, json=request)
    assert response.status_code == 201, response.text
    assert client.post(endpoint, json=request).json() == response.json()
    return prepared, response.json()


def settled(client, run_id):
    for _ in range(150):
        value = detail(client, run_id)
        if value['progress']['status'] != 'running':
            return value
        time.sleep(.01)
    pytest.fail('Recipe step did not settle.')


def test_recipe_steps_are_explicit_frozen_and_produce_one_unapplied_proposal(client, story):
    _, _, body = setup(client, story)
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    assert not provider.calls and detail(client, run_id)['jobs'] == []
    prepared = []
    for index, count in enumerate([1, 2, 1]):
        step, _ = start_step(client, run_id)
        prepared.extend(step['jobs'])
        assert step['request_count'] == count and step['provider_cost'] is None
        value = settled(client, run_id)
        assert value['revision'] == index + 1
        assert value['progress']['status'] == ('complete' if index == 2 else 'ready')
        assert len(provider.calls) == len(prepared)
        if index < 2:
            assert value['proposals'] == []
    assert [(call[1], call[2]) for call in provider.calls] == [(job['instructions'], job['content']) for job in prepared]
    assert len(value['proposals']) == 1 and value['proposal_id'] == value['proposals'][0]['id']
    proposal = value['proposals'][0]
    assert proposal['status'] == 'pending' and proposal['origin']['kind'] == 'recipe'
    assert target(client, body['target'])['text'] == body['selection']['text']
    receipt = apply(client, proposal)
    assert target(client, body['target'])['text'] == proposal['replacement']
    undo(client, receipt)
    assert target(client, body['target'])['text'] == body['selection']['text']
    assert client.post(f'/api/recipe-runs/{run_id}/preview-step').status_code == 409
    assert 'credential_ref' not in encode(value)


@pytest.mark.parametrize('mode', ['invalid', 'foreign', 'authority', 'partial', 'length', 'uncertain'])
def test_failed_recipe_outputs_cannot_advance_or_offer_applicable_text(client, story, mode):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider(mode)
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    start_step(client, run_id)
    value = settled(client, run_id)
    assert value['progress']['status'] == 'needs-attention' and value['proposals'] == []
    job = value['jobs'][0]
    assert job['status'] == 'error' and job['result'] is None and job['output']
    assert client.post(f'/api/recipe-runs/{run_id}/preview-step').status_code == 409
    provider.mode = 'valid'
    assert client.post(f"/api/recipe-jobs/{job['id']}/retry").status_code == 200
    retried = settled(client, run_id)
    assert retried['progress']['status'] == 'complete'
    assert provider.calls[0] == provider.calls[1]
    attempts = client.get(f"/api/recipe-jobs/{job['id']}/attempts").json()
    assert [attempt['status'] for attempt in attempts] == ['error', 'done']


def test_recipe_changed_target_returns_conflict_without_overwriting_new_text(client, story):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    save_document(client, target(client, body['target']), 'A newer author draft.')
    start_step(client, run_id)
    value = settled(client, run_id)
    assert value['proposals'][0]['status'] == 'conflict'
    assert target(client, body['target'])['text'] == 'A newer author draft.'
    assert decode(provider.calls[0][2])['sources'][0]['text'] == body['selection']['text']


def test_recipe_cancel_and_current_workspace_ceiling_guard_explicit_retry(client, story):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider('wait')
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    _, started = start_step(client, run_id)
    job_id = started['job_ids'][0]
    for _ in range(100):
        if provider.calls:
            break
        time.sleep(.01)
    assert provider.calls
    for _ in range(100):
        running = detail(client, run_id)['jobs'][0]
        if running['output']:
            break
        time.sleep(.01)
    assert running['status'] == 'running' and running['output'] and running['result'] is None
    assert client.post(f'/api/recipe-jobs/{job_id}/stop').status_code == 200
    value = settled(client, run_id)
    assert value['jobs'][0]['status'] == 'cancelled' and value['jobs'][0]['output']
    with client.app.state.database.connect(write=True) as connection:
        set_agents(connection, ['writer'], False, switch_state(connection)['revision'])
    assert client.post(f'/api/recipe-jobs/{job_id}/retry').status_code == 409
    assert len(provider.calls) == 1


def test_review_only_recipe_never_creates_a_text_proposal(client, story):
    _, _, body = setup(client, story, {'purpose': 'review', 'steps': [{'task': 'review', 'lenses': ['dialogue']}]})
    client.app.state.recipe_runner.provider = RecipeProvider()
    run_id = create_run(client, story, body)
    start_step(client, run_id)
    value = settled(client, run_id)
    assert value['progress']['status'] == 'complete' and value['proposal_id'] is None and value['proposals'] == []


def test_stale_recipe_attempt_commands_cannot_control_newer_attempts(client, story):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider('invalid')
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    start_step(client, run_id)
    job = settled(client, run_id)['jobs'][0]
    endpoint = f"/api/recipe-jobs/{job['id']}"
    assert job['attempt'] == 1
    provider.mode = 'wait'
    assert client.post(endpoint + '/retry', json={'expected_attempt': 0}).status_code == 409
    assert client.post(endpoint + '/retry', json={'expected_attempt': 1}).status_code == 200
    for _ in range(100):
        if len(provider.calls) == 2:
            break
        time.sleep(.01)
    assert len(provider.calls) == 2
    assert client.post(endpoint + '/stop', json={'expected_attempt': 1}).status_code == 409
    assert detail(client, run_id)['jobs'][0]['status'] == 'running'
    assert client.post(endpoint + '/stop', json={'expected_attempt': 2}).status_code == 200
    job = settled(client, run_id)['jobs'][0]
    assert job['status'] == 'cancelled' and job['attempt'] == 2
    assert client.post(endpoint + '/retry', json={'expected_attempt': 1}).status_code == 409
    provider.mode = 'valid'
    assert client.post(endpoint + '/retry', json={'expected_attempt': 2}).status_code == 200
    assert settled(client, run_id)['progress']['status'] == 'complete'
    assert len(provider.calls) == 3


def test_queued_recipe_stop_checks_the_upcoming_attempt(client, story, monkeypatch):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider()
    runner = client.app.state.recipe_runner
    runner.provider = provider
    monkeypatch.setattr(runner, 'start', lambda job_id: None)
    run_id = create_run(client, story, body)
    _, started = start_step(client, run_id)
    endpoint = f"/api/recipe-jobs/{started['job_ids'][0]}/stop"
    assert client.post(endpoint, json={'expected_attempt': 0}).status_code == 409
    assert client.post(endpoint, json={'expected_attempt': 1}).status_code == 200
    assert detail(client, run_id)['jobs'][0]['status'] == 'cancelled'
    assert provider.calls == []


def test_two_views_cannot_advance_a_recipe_step_twice(client, story):
    _, _, body = setup(client, story, {'steps': [{'task': 'writer'}]})
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    run_id = create_run(client, story, body)
    prepared = client.post(f'/api/recipe-runs/{run_id}/preview-step').json()
    request = {'expected_revision': prepared['revision'], 'preview_hash': prepared['preview_hash'], 'operation_id': uuid4().hex}
    endpoint = f'/api/recipe-runs/{run_id}/steps'
    first = client.post(endpoint, json=request)
    assert first.status_code == 201, first.text
    assert client.post(endpoint, json={**request, 'operation_id': uuid4().hex}).status_code == 409
    assert client.post(endpoint, json=request).json() == first.json()
    result = settled(client, run_id)
    assert len(provider.calls) == len(result['jobs']) == len(result['proposals']) == 1
    assert client.get('/api/recipe-runs/operations/' + request['operation_id']).json() == first.json()


def test_stale_run_preview_and_disabled_next_stage_do_not_start_work(client, story):
    from server.prompts import Prompts, PromptUpdate
    _, _, body = setup(client, story)
    provider = RecipeProvider()
    client.app.state.recipe_runner.provider = provider
    planned = preview(client, story, body)
    prompt = next(item for item in client.get('/api/prompts').json() if item['key'] == 'writer')
    Prompts(client.app.state.database).update('writer', PromptUpdate(expected_version_id=prompt['id'], template='Changed author instructions.'))
    response = client.post(f"/api/branches/{story['branch_id']}/recipe-runs", json={
        **body, 'preview_hash': planned['preview_hash'], 'operation_id': uuid4().hex})
    assert response.status_code == 409 and not provider.calls
    run_id = create_run(client, story, body)
    prepared = client.post(f'/api/recipe-runs/{run_id}/preview-step').json()
    with client.app.state.database.connect(write=True) as connection:
        set_agents(connection, ['writer'], False, switch_state(connection)['revision'])
    before = database_dump(client)
    response = client.post(f'/api/recipe-runs/{run_id}/steps', json={
        'expected_revision': prepared['revision'], 'preview_hash': prepared['preview_hash'], 'operation_id': uuid4().hex})
    assert response.status_code == 409 and database_dump(client) == before and not provider.calls
