"""Build labeled workflow history through real services and test-only providers."""
from copy import deepcopy
from uuid import uuid4

from pytest import MonkeyPatch

from server.database import decode
from tests.test_assessments import AssessmentProvider, settled
from tests.test_generations import DraftProvider, finished
from tests.test_mechanics import configure
from tests.test_scene_chance import BOUNDARY, no_event_seed
from tests.test_scene_continuity import acceptance_body, ready_continuity
from tests.test_scene_patches import selected_stage
from tests.test_scenes import PLAN
from tests.test_sidebar import CollaboratorProvider, ask, settle, thread


def fixture_profile(client, name):
    response = client.post('/api/profiles', json={'name': name, 'config': {
        'provider': 'local', 'model': 'synthetic-benchmark-only',
        'base_url': 'http://127.0.0.1:9/v1', 'context_tokens': 2000000}})
    assert response.status_code == 201, response.text
    return response.json()['profile_id']


def continuity_changes(output, count):
    template = output['changes'][0]
    output['changes'] = [{**deepcopy(template), 'id': f'c{index + 1}',
        'kind': ('fact', 'knowledge', 'thread')[index % 3],
        'subject': f'Benchmark continuity {index + 1:03d}',
        'text': f'Synthetic continuity marker {index + 1:03d}: the sealed letter remains unexamined.'}
        for index in range(count)]


def accepted_scene(client, story, changes=None):
    run_id, provider = ready_continuity(client, story)
    selected = ['c1', 'c2']
    if changes is not None:
        provider.corrupt = lambda output: continuity_changes(output, changes)
        selected_stage(client, run_id, 'scene-continuity')
        selected = [f'c{index + 1}' for index in range(changes)]
    body = acceptance_body(client, run_id, selected_ids=selected)
    response = client.post(f'/api/scenes/{run_id}/accept', json=body)
    assert response.status_code == 200, response.text
    return response.json()['state']['accepted']


def assessed_alternatives(client, story, profiles, count):
    client.app.state.assessment_runner.provider = AssessmentProvider()
    client.app.state.runner.provider = DraftProvider()
    run_ids = []
    for _ in range(count):
        revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
        response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
            'operation_id': uuid4().hex, 'expected_revision': revision, 'profile_ids': profiles})
        assert response.status_code == 201, response.text
        run = settled(client, response.json()['assessment_id'])
        assert run['generation_id'], run
        generation = finished(client, run['generation_id'])
        candidate_id = generation['candidates'][0]['id']
        accepted = client.post(f'/api/candidates/{candidate_id}/accept', json={'operation_id': uuid4().hex})
        assert accepted.status_code == 200, accepted.text
        run_ids.append(run['id'])
    return run_ids


def sidebar_history(client, story, count):
    client.app.state.side_runner.provider = CollaboratorProvider()
    thread_id = thread(client, story)
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    for _ in range(count):
        ask(client, thread_id, story, revision)
        settle(client)
    return thread_id


def seed_workflow(client, story, profiles, size):
    configure(client, story, automatic_assessment=True, chance=100, cooldown=0)
    with MonkeyPatch.context() as patch:
        seed = no_event_seed(client)
        patch.setattr('server.scenes.chance.secrets.token_hex', lambda _length: seed)
        patch.setitem(PLAN['beats'][0], 'chance', dict(BOUNDARY))
        early = accepted_scene(client, story, size.continuity_entries)
        later = accepted_scene(client, story)
        assessments = assessed_alternatives(client, story, profiles, size.assessments)
        sidebar = sidebar_history(client, story, size.sidebar_turns)
    return {'early_receipt': early, 'later_receipt': later, 'assessment_ids': assessments,
            'sidebar_thread_id': sidebar, 'rng_seed': seed,
            'label': 'Synthetic test providers only; served app keeps real adapters.'}


def pending_jobs(connection):
    tables = ('candidates', 'assessment_jobs', 'scene_jobs', 'review_jobs', 'side_replies', 'background_jobs')
    return {table: connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE status IN ('queued','running')").fetchone()[0]
        for table in tables}


def frozen_input_bytes(connection):
    tables = ('generations', 'assessment_runs', 'assessment_jobs', 'scene_runs', 'scene_jobs',
              'review_runs', 'review_jobs', 'side_turns', 'background_runs', 'background_jobs')
    result = {}
    for table in tables:
        rows = connection.execute(f'SELECT snapshot FROM {table}').fetchall()
        result[table] = {'records': len(rows), 'snapshot_utf8_bytes': sum(len(row[0].encode('utf-8')) for row in rows)}
        assert all(isinstance(decode(row[0]), dict) for row in rows)
    return result
