from uuid import uuid4

import pytest

from server.assessment.writing import WritingRequests
from server.database import encode
from server.generation_models import GenerateRequest
from tests.test_assessments import setup_assessment
from tests.test_context_contract import revise_prompt
from tests.test_context_inspector import database_dump
from tests.test_generations import DraftProvider, finished
from tests.test_mechanics import prepare
from tests.test_profiles import make_profile


def during_assembly(monkeypatch, action):
    from server.generation_context import assemble_memory
    ran = []

    def assemble(*args, **kwargs):
        if not ran:
            ran.append(True)
            action()
        return assemble_memory(*args, **kwargs)

    monkeypatch.setattr('server.generation_context.assemble_memory', assemble)
    return ran


def test_unrelated_database_write_can_finish_during_read_only_assembly(client, story, monkeypatch):
    make_profile(client, 'Writer', primary=True)
    database = client.app.state.database

    def stream_progress():
        with database.connect(write=True) as connection:
            connection.execute('INSERT INTO preferences VALUES (?,?)', ('test-stream-progress', encode('saved')))

    ran = during_assembly(monkeypatch, stream_progress)
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=0)
    result = WritingRequests(database).create(story['branch_id'], body)
    assert result['id'] and ran
    with database.connect() as connection:
        assert connection.execute("SELECT value FROM preferences WHERE key='test-stream-progress'").fetchone()


@pytest.mark.parametrize('change', ['prompt', 'profile', 'branch', 'opportunity'])
def test_source_changes_during_preparation_fail_before_recording(client, story, monkeypatch, change):
    profile = setup_assessment(client, story)

    def change_inputs():
        if change == 'prompt':
            revise_prompt(client)
        if change == 'profile':
            response = client.put(f"/api/profiles/{profile['profile_id']}", json={
                'expected_version_id': profile['id'], 'name': 'Revised', 'config': profile['config']})
            assert response.status_code == 200
        if change == 'branch':
            from server.branches import Branches
            from server.models import MessageCreate
            Branches(client.app.state.database).append(story['branch_id'], MessageCreate(
                operation_id=uuid4().hex, expected_revision=1, role='narrator', text='A new event.'))
        if change == 'opportunity':
            prepare(client, story['branch_id'], revision=1)

    during_assembly(monkeypatch, change_inputs)
    monkeypatch.setattr('server.assessment.preparation.seed_assessment', lambda *_: pytest.fail('Uncommitted request seeded'))
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 1})
    assert response.status_code == 409, response.text
    assert 'while context was being assembled' in response.json()['detail']
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []
    assert client.app.state.assessment_runner.provider.calls == []


def test_full_history_preview_does_not_create_a_disk_index(client, story):
    make_profile(client, 'Writer', primary=True)
    before = database_dump(client)
    response = client.post(f"/api/branches/{story['branch_id']}/context-preview", json={'expected_revision': 0})
    assert response.status_code == 200
    assert database_dump(client) == before
    path = client.app.state.database.path
    assert not (path.parent / '.cache' / (path.name + '.memory.sqlite3')).exists()


def test_existing_boundary_does_not_resolve_an_unused_assessor_profile(client, story):
    setup_assessment(client, story)
    prepare(client, story['branch_id'], revision=1)
    database = client.app.state.database
    with database.connect(write=True) as connection:
        from server.database import decode
        settings = decode(connection.execute('SELECT settings FROM stories WHERE id=?', (story['story_id'],)).fetchone()[0])
        settings['step_profiles'] = {'beat-assessment': 'unavailable-but-unused'}
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
    client.app.state.runner.provider = DraftProvider()
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 1, 'use_prepared_beat': False})
    assert response.status_code == 201, response.text
    assert finished(client, response.json()['id'])['candidates'][0]['status'] == 'done'


def test_two_concurrent_requests_with_one_operation_record_and_dispatch_once(client, story, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from server.generation_context import assemble_memory
    make_profile(client, 'Writer', primary=True)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    barrier = Barrier(2)

    def assemble(*args, **kwargs):
        barrier.wait(timeout=5)
        return assemble_memory(*args, **kwargs)

    monkeypatch.setattr('server.generation_context.assemble_memory', assemble)
    endpoint = f"/api/branches/{story['branch_id']}/generations"
    request = {'operation_id': uuid4().hex, 'expected_revision': 0}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, endpoint, json=request) for _ in range(2)]
        responses = [future.result(timeout=10) for future in futures]
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json() == responses[1].json()
    generation = finished(client, responses[0].json()['id'])
    assert len(generation['candidates']) == len(provider.calls) == 1
