from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.mechanics.engine import resolve_beat
from server.mechanics.models import Beat, RngSettings
from server.mechanics.state import initial_state
from server.mechanics.tables import catalog
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_mechanics import configure, counts, prepare
from tests.test_profiles import make_profile
from tests.test_scene_continuity import acceptance_body, ready_continuity
from tests.test_scene_drafting import DraftProvider
from tests.test_scenes import (
    PLAN,
    SceneProvider,
    choose,
    decide,
    finish_plan,
    get_plan,
    ready_plan,
    run_stage,
)

BOUNDARY = {'completed': True, 'waiting_for_player': False, 'family': 'encounter'}


def no_event_seed(client):
    with client.app.state.database.connect() as connection:
        versions = catalog(connection)
    settings = RngSettings(enabled=True, chance=100, cooldown=0)
    for index in range(100):
        seed = f'no-event-fixture-{index}'
        result = resolve_beat(versions, settings, Beat(label='Boundary', family='encounter'), initial_state(), seed)
        if result['event']['status'] == 'no_event':
            return seed
    raise AssertionError('Deterministic no-event fixture was not found.')


def seeded_chance(client, monkeypatch):
    seed = no_event_seed(client)
    monkeypatch.setattr('server.scenes.chance.secrets.token_hex', lambda _length: seed)
    monkeypatch.setitem(PLAN['beats'][0], 'chance', BOUNDARY)


def test_disabled_scene_approval_makes_no_draws_or_mechanic_records(client, story, monkeypatch):
    monkeypatch.setitem(PLAN['beats'][0], 'chance', BOUNDARY)
    def forbidden(_length):
        raise AssertionError('Disabled scene randomness requested a seed.')
    monkeypatch.setattr('server.scenes.chance.secrets.token_hex', forbidden)
    run_id, _ = ready_plan(client, story)
    before = counts(client)
    result = decide(client, run_id, 'approve')
    assert 'mechanics' not in result['state']['gate_a']
    assert counts(client) == before
    client.app.state.scene_runner.provider = DraftProvider()
    job = run_stage(client, run_id, 'scene-draft')[0]
    assert not any(source['id'] == 'scene:saved-chance' for source in decode(job['snapshot']['content'])['sources'])


def test_schedule_skips_ineligible_boundaries_and_preserves_cadence_and_no_event(client, story, monkeypatch):
    configure(client, story, chance=100, cooldown=2)
    seeded_chance(client, monkeypatch)
    beats = []
    for index in range(5):
        beats.append({**deepcopy(PLAN['beats'][0]), 'id': f'b{index}', 'title': f'Boundary {index}', 'chance': dict(BOUNDARY)})
    beats[0]['chance']['waiting_for_player'] = True
    beats[2]['chance']['protected'] = True
    monkeypatch.setitem(PLAN, 'beats', beats)
    run_id, _ = ready_plan(client, story)
    branch_before = client.get(f"/api/branches/{story['branch_id']}").json()
    schedule = decide(client, run_id, 'approve')['state']['gate_a']['mechanics']
    results = [item['result'] for item in schedule['entries']]
    assert results[0]['eligibility'] and results[2]['eligibility']
    assert [results[index]['event']['status'] for index in (1, 3, 4)] == ['cooldown', 'cooldown', 'no_event']
    assert [len(result['draws']) for result in results] == [0, 0, 0, 0, 2]
    assert schedule['after']['beat'] == 3 and schedule['after']['cooldown'] == 2
    assert not schedule['after']['unresolved_event']
    assert client.get(f"/api/branches/{story['branch_id']}").json() == branch_before


def test_scene_chance_is_reused_through_acceptance_and_archive_recovery(client, story, monkeypatch):
    configure(client, story, chance=100, cooldown=0)
    seeded_chance(client, monkeypatch)
    run_id, _ = ready_continuity(client, story)
    run = get_plan(client, run_id)
    schedule = run['state']['gate_a']['mechanics']
    for job in run['jobs']:
        if job['step'] in {'scene-options', 'scene-beats', 'scene-brief'}:
            continue
        source = next(source for source in decode(job['snapshot']['content'])['sources'] if source['id'] == 'scene:saved-chance')
        qualitative = decode(source['text'])
        assert set(qualitative) == {'status', 'prepared_opening', 'beats'}
        assert set(qualitative['beats'][0]) == {'beat_id', 'title', 'instructions', 'skip_reason'}
        assert '"seed"' not in source['text'] and '"draws"' not in source['text']
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert before['mechanics']['state'] == schedule['before']
    body = acceptance_body(client, run_id)
    accepted = client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert accepted.status_code == 200, accepted.text
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).json() == accepted.json()
    after = client.get(f"/api/branches/{story['branch_id']}").json()
    assert after['mechanics']['state'] == schedule['after']
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={'operation_id': uuid4().hex,
        'expected_revision': after['revision'], 'node_id': before['head_id'], 'name': 'Before the scheduled scene'}).json()
    assert client.get(f"/api/branches/{fork['branch_id']}").json()['mechanics']['state'] == schedule['before']
    file, document = backup(client, story)
    assert document['version'] == 19
    _, mapping = restore(client, file)
    restored = get_plan(client, mapping[run_id])
    assert restored['state']['gate_a']['mechanics']['after'] == schedule['after']
    assert [job['snapshot']['content'] for job in restored['jobs']] == [job['snapshot']['content'] for job in run['jobs']]
    frozen = restored['state']['gate_a']['mechanics']['entries'][0]['result']
    assert all(version in mapping.values() for version in frozen['settings']['table_versions'].values())
    assert restored['snapshot']['settings']['table_versions'] != run['snapshot']['settings']['table_versions']


def test_changed_settings_block_fresh_draws_and_failed_approval_rolls_back(client, story, monkeypatch):
    configure(client, story, chance=100, cooldown=0)
    seeded_chance(client, monkeypatch)
    run_id, _ = ready_plan(client, story)
    before = get_plan(client, run_id)
    def fail(*_args):
        raise RuntimeError('transaction fixture')
    with monkeypatch.context() as patch:
        patch.setattr('server.scenes.service.save_decision', fail)
        with pytest.raises(RuntimeError, match='transaction fixture'):
            decide(client, run_id, 'approve')
    assert get_plan(client, run_id) == before
    configure(client, story, enabled=False)
    assert get_plan(client, run_id)['stale']
    response = client.post(f'/api/scenes/{run_id}/approve', json={'operation_id': uuid4().hex, 'expected_revision': before['revision']})
    assert response.status_code == 409 and not get_plan(client, run_id)['state']['gate_a']


def test_archive_rejects_altered_schedule_without_rerolling(client, story, monkeypatch):
    configure(client, story, chance=100, cooldown=0)
    seeded_chance(client, monkeypatch)
    run_id, _ = ready_plan(client, story)
    decide(client, run_id, 'approve')
    _, document = backup(client, story)
    row = next(row for row in document['data']['scene_runs'] if row['id'] == run_id)
    state = decode(row['state'])
    state['gate_a']['mechanics']['entries'][0]['result']['draws'][0]['result'] = 0
    row['state'] = encode(state)
    response = client.post('/api/archives/imports', json={'content': encode(document)})
    assert response.status_code == 400


def test_prepared_manual_beat_is_reused_with_automatic_chance_off(client, story):
    make_profile(client, 'Fixture planner', primary=True)
    append(client, story['branch_id'], 'Fixture: a completed introduction.', 0)
    prepared = prepare(client, story['branch_id'], revision=1, manual=True)
    client.app.state.scene_runner.provider = SceneProvider()
    created = client.post(f"/api/branches/{story['branch_id']}/scenes", json={'operation_id': uuid4().hex,
        'expected_revision': 1, 'title': 'Reuse the prepared opening', 'direction': 'Fixture only.', 'propose_options': False}).json()
    run_id = created['id']
    for key in ('scene-beats', 'scene-brief'):
        choose(client, run_id, run_stage(client, run_id, key)[0])
    before = counts(client)
    schedule = decide(client, run_id, 'approve')['state']['gate_a']['mechanics']
    assert schedule['entries'] == [] and schedule['inherited']['opportunity_id'] == prepared['id']
    assert schedule['after']['last_opportunity_id'] == prepared['id']
    assert counts(client) == before
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = get_plan(client, mapping[run_id])['state']['gate_a']['mechanics']
    assert restored['after']['last_opportunity_id'] == mapping[prepared['id']]
    assert restored['inherited']['opportunity_id'] == mapping[prepared['id']]


def test_comparison_retry_and_archive_validation_never_redraw(client, story, monkeypatch):
    configure(client, story, chance=100, cooldown=0)
    seeded_chance(client, monkeypatch)
    run_id, _ = ready_plan(client, story)
    saved = decide(client, run_id, 'approve')['state']['gate_a']
    def forbidden(_length):
        raise AssertionError('A later stage attempted to roll again.')
    monkeypatch.setattr('server.scenes.chance.secrets.token_hex', forbidden)
    profiles = [make_profile(client, name)['profile_id'] for name in ('Comparison A', 'Comparison B')]
    provider = DraftProvider()
    provider.corrupt = lambda result: result.update(blocks=[])
    client.app.state.scene_runner.provider = provider
    jobs = run_stage(client, run_id, 'scene-draft', profiles)
    assert [job['status'] for job in jobs] == ['error', 'error']
    assert jobs[0]['snapshot']['content'] == jobs[1]['snapshot']['content']
    provider.corrupt = None
    assert client.post(f"/api/scene-jobs/{jobs[0]['id']}/retry").status_code == 200
    retried = next(job for job in finish_plan(client, run_id)['jobs'] if job['id'] == jobs[0]['id'])
    assert retried['status'] == 'done' and retried['attempt'] == 2
    assert retried['snapshot'] == jobs[0]['snapshot']
    choose(client, run_id, retried)
    assert get_plan(client, run_id)['state']['gate_a'] == saved
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert get_plan(client, mapping[run_id])['state']['gate_a']['mechanics']['after'] == saved['mechanics']['after']
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})


def test_failed_acceptance_rolls_back_scene_state_and_continuity(client, story, monkeypatch):
    configure(client, story, chance=100, cooldown=0)
    seeded_chance(client, monkeypatch)
    run_id, _ = ready_continuity(client, story)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    run_before, records = get_plan(client, run_id), counts(client)
    body = acceptance_body(client, run_id)
    def fail(*_args):
        raise RuntimeError('acceptance transaction fixture')
    with monkeypatch.context() as patch:
        patch.setattr('server.scenes.service.save_decision', fail)
        with pytest.raises(RuntimeError, match='acceptance transaction fixture'):
            client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert counts(client) == records
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert client.get(f"/api/branches/{story['branch_id']}/continuity").json() == {'entries': [], 'commits': []}
    assert get_plan(client, run_id) == run_before
    assert client.post(f'/api/scenes/{run_id}/accept', json=body).status_code == 200
