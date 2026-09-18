"""Planned-state semantics and actual continuity acceptance; scripted outputs are not quality evidence."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from server.archives.format import ARCHIVE_VERSION, PLAN_TABLES
from server.continuity import continuity_sources
from server.database import decode, encode, one
from server.errors import DomainError
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.memory.planned_events import PlannedEvent, plan_entry_fields, validate_plan_update
from server.providers.events import ProviderEvent
from server.scenes.continuity_models import ContinuityChange
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_scene_continuity import acceptance_body, continuity, ready_continuity
from tests.test_scene_patches import ready_patch, selected_stage
from tests.test_scenes import get_plan

AGREEMENT = 'On Friday evening, Mara and Jules agreed to go camping together this weekend.'
WITHDRAWAL = 'Mara said, "I cannot go this weekend." Jules said, "I still intend to go camping."'
CANCELLATION = 'Mara and Jules agreed to cancel the camping trip altogether.'


def plan(status='agreed'):
    return {'status': status, 'participants': [
        {'id': 'mara', 'name': 'Mara', 'commitment': 'agreed'},
        {'id': 'jules', 'name': 'Jules', 'commitment': 'agreed'}],
        'timing': 'this weekend', 'time_anchor': 'Friday evening when the agreement was made',
        'resolution': None}


def change(value=None, *, target=None, quote=AGREEMENT):
    return {'id': 'camping', 'action': 'replace' if target else 'add', 'target_id': target,
            'kind': 'plan', 'subject': 'Camping trip', 'text': quote,
            'reason': 'Explicit expected interpretation supplied by this test fixture.',
            'evidence': [{'source_id': 'scene:checked', 'quote': quote}], 'plan': value or plan()}


class PlanFixtureProvider:
    def __init__(self, proposed):
        self.proposed = proposed

    async def generate(self, _profile, _prompt, content):
        context = decode(content)
        text = next(source['text'] for source in context['sources'] if source['id'] == 'scene:checked')
        result = {'summary': 'Scripted plan proposal; no model inference tested.', 'scene_summary': text,
                  'summary_quote': text, 'changes': [self.proposed]}
        yield ProviderEvent(text=encode(result), done=True)


def accept_plan(client, story, prose, proposed):
    run_id, patch = ready_patch(client, story)
    patch.corrupt = lambda result: result['edits'][0].update(after=prose)
    selected_stage(client, run_id, 'scene-patch')
    patch.corrupt = None
    selected_stage(client, run_id, 'scene-patch-check')
    client.app.state.scene_runner.provider = PlanFixtureProvider(proposed)
    selected_stage(client, run_id, 'scene-continuity')
    response = client.post(f'/api/scenes/{run_id}/accept',
                           json=acceptance_body(client, run_id, selected_ids=['camping'], include_summary=False))
    assert response.status_code == 200, response.text
    return run_id, response.json()['state']['accepted']


def writer_context(client, branch_id):
    with client.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        snapshot, _ = generation_snapshot(connection, branch_id, GenerateRequest(
            operation_id=uuid4().hex, expected_revision=branch['revision'],
            direction='Continue after the refusal.', use_prepared_beat=False))
    return decode(snapshot['content'])


def fork(client, branch_id, node_id, **extra):
    branch = client.get(f'/api/branches/{branch_id}').json()
    result = client.post(f'/api/branches/{branch_id}/forks', json={
        'operation_id': uuid4().hex, 'expected_revision': branch['revision'],
        'node_id': node_id, 'name': 'Alternate plan', **extra})
    assert result.status_code == 201, result.text
    return result.json()['branch_id']


def test_participant_withdrawal_preserves_trip_and_branch_history(client, story):
    run_id, first = accept_plan(client, story, AGREEMENT, change())
    original = continuity(client, story['branch_id'])
    entry_id = original['entries'][0]['id']
    before_inputs = [job['snapshot']['content'] for job in get_plan(client, run_id)['jobs']]
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    append(client, story['branch_id'], 'They spent the afternoon repairing a cupboard.', branch['revision'])
    revised = plan()
    revised['participants'][0]['commitment'] = 'withdrawn'
    accept_plan(client, story, WITHDRAWAL, change(revised, target=entry_id, quote=WITHDRAWAL))
    current = continuity(client, story['branch_id'])
    entry = current['entries'][0]
    assert entry['status'] == 'active' and entry['plan']['status'] == 'agreed'
    assert [person['commitment'] for person in entry['plan']['participants']] == ['withdrawn', 'agreed']
    assert writer_context(client, story['branch_id'])['continuity']['entries'][0]['plan'] == revised
    assert decode(continuity_sources(current)[0]['text'])['plan'] == revised
    earlier = fork(client, story['branch_id'], first['node_id'])
    assert continuity(client, earlier) == original
    edited = fork(client, story['branch_id'], first['node_id'], replacement='Mara never proposed a trip.')
    assert continuity(client, edited)['entries'] == []
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    copied = continuity(client, mapping[story['branch_id']])
    assert copied['entries'][0]['plan'] == revised
    assert copied['entries'][0]['id'] == entry_id
    assert continuity(client, mapping[earlier])['entries'][0]['plan'] == plan()
    assert continuity(client, mapping[edited])['entries'] == []
    assert [job['snapshot']['content'] for job in get_plan(client, mapping[run_id])['jobs']] == before_inputs
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})


def test_cancelled_plan_has_distinct_outcome_and_prior_branch_stays_open(client, story):
    _, first = accept_plan(client, story, AGREEMENT, change())
    current = continuity(client, story['branch_id'])
    cancelled = plan('cancelled')
    cancelled['resolution'] = 'Both participants explicitly cancelled the trip.'
    accept_plan(client, story, CANCELLATION,
                change(cancelled, target=current['entries'][0]['id'], quote=CANCELLATION))
    entry = continuity(client, story['branch_id'])['entries'][0]
    assert entry['status'] == 'resolved' and entry['plan']['status'] == 'cancelled'
    earlier = fork(client, story['branch_id'], first['node_id'])
    assert continuity(client, earlier)['entries'][0]['status'] == 'active'


@pytest.mark.parametrize('state', ['proposed', 'agreed', 'postponed', 'attempted', 'uncertain'])
def test_open_plans_do_not_become_completed_from_status_or_past_date(state):
    proposed = change(plan(state))
    proposed['plan']['timing'] = 'yesterday'
    validated = ContinuityChange.model_validate(proposed).model_dump()
    assert plan_entry_fields(validated)['status'] == 'active'
    assert validated['plan']['status'] == state


@pytest.mark.parametrize('state', ['completed', 'cancelled'])
def test_closed_plan_requires_recorded_outcome(state):
    with pytest.raises(ValidationError, match='explicit resolution'):
        PlannedEvent.model_validate(plan(state))
    completed = plan(state)
    completed['resolution'] = 'The accepted scene explicitly establishes the outcome.'
    assert plan_entry_fields(change(completed))['status'] == 'resolved'


def test_withdrawal_does_not_drop_participants_or_use_generic_thread_resolution():
    original = change()
    updated = change(target='existing')
    updated['plan']['participants'] = updated['plan']['participants'][1:]
    with pytest.raises(DomainError, match='Keep existing plan participants'):
        validate_plan_update(updated, original)
    updated = change(target='existing')
    updated['action'] = 'resolve'
    with pytest.raises(DomainError, match='explicit completed or cancelled'):
        validate_plan_update(updated, original)


def test_old_continuity_serialization_stays_identical():
    legacy = change()
    del legacy['plan']
    legacy['kind'] = 'thread'
    assert ContinuityChange.model_validate(legacy).model_dump() == legacy
    assert plan_entry_fields(legacy) == {}


def test_plan_shape_rejects_missing_details_duplicates_and_foreign_payloads():
    missing = change()
    del missing['plan']
    with pytest.raises(ValidationError, match='structured plan'):
        ContinuityChange.model_validate(missing)
    foreign = change()
    foreign['kind'] = 'fact'
    with pytest.raises(ValidationError, match='structured plan'):
        ContinuityChange.model_validate(foreign)
    duplicate = plan()
    duplicate['participants'].append(deepcopy(duplicate['participants'][0]))
    with pytest.raises(ValidationError, match='stable ID'):
        PlannedEvent.model_validate(duplicate)


def test_format_28_restore_preserves_legacy_inputs(client, story):
    run_id, _ = ready_continuity(client, story)
    response = client.post(f'/api/scenes/{run_id}/accept', json=acceptance_body(client, run_id))
    assert response.status_code == 200, response.text
    prior = continuity(client, story['branch_id'])
    frozen = [job['snapshot']['content'] for job in get_plan(client, run_id)['jobs']]
    _, document = backup(client, story)
    document['version'] = 28
    for table in PLAN_TABLES:
        assert document['data'].pop(table) == []
    response = client.post('/api/archives/imports', json={'content': encode(document)})
    assert response.status_code == 201, response.text
    _, mapping = restore(client, response.json())
    current = continuity(client, mapping[story['branch_id']])
    assert [(entry['id'], entry['text']) for entry in current['entries']] == [
        (entry['id'], entry['text']) for entry in prior['entries']]
    assert [job['snapshot']['content'] for job in get_plan(client, mapping[run_id])['jobs']] == frozen


def test_continuity_plan_prompt_preserves_custom_head_and_story_pin(client, story):
    from server.prompts import initialize_prompts, prompt_snapshot
    from server.scenes.catalog import BOUNDARY, SCENE_PROMPTS
    from server.scenes.continuity_catalog import PLANNED_CONTINUITY_PROMPT

    database = client.app.state.database
    with database.connect() as connection:
        current = prompt_snapshot(connection, 'scene-continuity')
        assert current['template'] == BOUNDARY + PLANNED_CONTINUITY_PROMPT
        assert 'scene-continuity-default-v2' == current['id']
        pinned_story = {'settings': encode({'prompt_versions': {'scene-continuity': 'scene-continuity-default-v1'}})}
        assert prompt_snapshot(connection, 'scene-continuity', pinned_story)['template'] == SCENE_PROMPTS['scene-continuity']
    response = client.put('/api/prompts/scene-continuity', json={
        'expected_version_id': current['id'], 'template': 'My custom continuity instructions.'})
    assert response.status_code == 200, response.text
    initialize_prompts(database)
    with database.connect() as connection:
        assert prompt_snapshot(connection, 'scene-continuity')['template'] == 'My custom continuity instructions.'
        assert prompt_snapshot(connection, 'scene-continuity', pinned_story)['template'] == SCENE_PROMPTS['scene-continuity']
