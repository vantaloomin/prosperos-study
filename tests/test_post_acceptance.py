import asyncio
import json
from uuid import uuid4

import pytest

from server.assessment.preparation import prepare_accepted
from server.assessment.service import Assessments
from server.assessment.writing import WritingRequests
from server.branches import Branches
from server.database import decode, encode
from server.generation_models import GenerateRequest
from server.models import MessageCreate
from tests.test_archives import backup, restore
from tests.test_assessments import AssessmentProvider, settled
from tests.test_generations import DraftProvider, finished
from tests.test_mechanics import configure
from tests.test_profiles import make_profile


def prepared(client, story):
    make_profile(client, 'Scribe', primary=True)
    configure(client, story, automatic_assessment=True, chance=100, cooldown=0)
    client.app.state.assessment_runner.provider = AssessmentProvider()
    client.app.state.runner.provider = DraftProvider()
    node = Branches(client.app.state.database).append(story['branch_id'], MessageCreate(
        operation_id=uuid4().hex, expected_revision=0, role='narrator', text='The exchange is finished.'))
    result = prepare_accepted(client.app.state.database, story['branch_id'], node['node_id'])
    return Assessments(client.app.state.database).detail(result['assessment_id'])


def write(client, story, **values):
    return WritingRequests(client.app.state.database).create(story['branch_id'], GenerateRequest(
        operation_id=uuid4().hex, expected_revision=1, **values))


def complete(client, run):
    asyncio.run(client.app.state.assessment_runner.run(run['jobs'][0]['id']))
    return Assessments(client.app.state.database).detail(run['id'])


def test_ready_assessment_prepares_one_roll_without_starting_writer_and_roundtrips(client, story):
    run = complete(client, prepared(client, story))
    assert run['snapshot']['purpose'] == 'post-acceptance'
    assert not run['generation_id'] and run['opportunity_id']
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []
    assert client.get(f"/api/branches/{story['branch_id']}").json()['mechanics']['state']['beat'] == 0
    first, second = write(client, story), write(client, story)
    snapshots = [client.get(f"/api/generations/{item['id']}").json()['snapshot'] for item in (first, second)]
    assert all(item['opportunity_id'] == run['opportunity_id'] for item in snapshots)
    assert snapshots[0]['content'] == snapshots[1]['content']
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/assessments/{mapping[run['id']]}").json()
    assert restored['jobs'][0]['snapshot']['content'] == run['jobs'][0]['snapshot']['content']
    assert not restored['generation_id']
    frozen = decode(document['data']['assessment_runs'][0]['snapshot'])
    frozen['seed'] = 'bad seed'
    document['data']['assessment_runs'][0]['snapshot'] = encode(frozen)
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


def test_pending_result_cannot_attach_after_write_or_retry(client, story):
    run = prepared(client, story)
    generation = write(client, story)
    snapshot = client.get(f"/api/generations/{generation['id']}").json()['snapshot']
    assert snapshot['opportunity_id'] is None
    done = complete(client, run)
    assert done['stopped'] and not done['opportunity_id'] and not done['generation_id']
    assert client.get(f"/api/generations/{generation['id']}").json()['snapshot'] == snapshot
    assert client.post(f"/api/assessment-jobs/{run['jobs'][0]['id']}/retry").status_code == 409
    assert 'id' in write(client, story)


@pytest.mark.parametrize('change', ['story', 'branch', 'prompt', 'disabled', 'profile'])
def test_changed_preparation_never_supplies_chance(client, story, change):
    run = prepared(client, story)
    with client.app.state.database.connect(write=True) as connection:
        if change == 'story':
            connection.execute('UPDATE stories SET revision=revision+1 WHERE id=?', (story['story_id'],))
        if change == 'branch':
            connection.execute('UPDATE branches SET revision=revision+1 WHERE id=?', (story['branch_id'],))
        if change == 'disabled':
            connection.execute("INSERT INTO preferences VALUES ('agent_switches',?)", (encode({'revision': 1, 'disabled': ['scribe']}),))
        if change == 'prompt':
            connection.execute("UPDATE prompt_heads SET version_id='beat-assessment-default-v1' WHERE key='beat-assessment'")
            # A deliberate pin to the old task is a configuration change too.
            row = connection.execute('SELECT settings FROM stories WHERE id=?', (story['story_id'],)).fetchone()
            settings = decode(row['settings'])
            settings['prompt_versions'] = {'beat-assessment': 'beat-assessment-default-v1'}
            connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
    if change == 'profile':
        make_profile(client, 'Another scribe', primary=True)
    done = complete(client, run)
    assert done['stale'] and not done['opportunity_id'] and not done['generation_id']


def test_acceptance_starts_bookkeeping_once_and_write_never_starts_an_assessor(client, story):
    make_profile(client, 'Scribe', primary=True)
    configure(client, story, automatic_assessment=True, chance=100, cooldown=0)
    provider = AssessmentProvider()
    client.app.state.assessment_runner.provider = provider
    client.app.state.runner.provider = DraftProvider()
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'role': 'narrator', 'text': 'The exchange is finished.'}
    response = client.post(f"/api/branches/{story['branch_id']}/messages", json=body)
    assert response.status_code == 201, response.text
    runs = client.get(f"/api/branches/{story['branch_id']}/assessments").json()
    assert len(runs) == 1
    run = settled(client, runs[0]['id'])
    assert run['opportunity_id'] and not run['generation_id']
    client.post(f"/api/branches/{story['branch_id']}/messages", json=body)
    request = client.post(f"/api/branches/{story['branch_id']}/generations", json={'operation_id': uuid4().hex, 'expected_revision': 1})
    assert request.status_code == 201 and 'id' in request.json()
    finished(client, request.json()['id'])
    assert len(provider.calls) == 1


def test_failed_assessment_and_ooc_never_block_writer(client, story):
    run = prepared(client, story)
    client.app.state.assessment_runner.provider = AssessmentProvider(invalid=True)
    done = complete(client, run)
    assert done['jobs'][0]['status'] == 'error'
    assert 'id' in write(client, story)
    node = Branches(client.app.state.database).append(story['branch_id'], MessageCreate(
        operation_id=uuid4().hex, expected_revision=1, role='ooc', text='Author note.'))
    assert prepare_accepted(client.app.state.database, story['branch_id'], node['node_id']) is None


def test_completion_during_writer_assembly_does_not_change_the_frozen_request(client, story, monkeypatch):
    from tests.test_generation_preparation import during_assembly
    run = prepared(client, story)
    during_assembly(monkeypatch, lambda: complete(client, run))
    generation = write(client, story)
    snapshot = client.get(f"/api/generations/{generation['id']}").json()['snapshot']
    assert snapshot['opportunity_id'] is None
    assert 'prepared_beat' not in decode(snapshot['content'])
    current = Assessments(client.app.state.database).detail(run['id'])
    assert current['stopped']
    assert client.get(f"/api/branches/{story['branch_id']}").json()['mechanics']['pending'] is None


def test_ready_result_changed_during_assembly_requires_a_fresh_writer_preview(client, story, monkeypatch):
    from server.errors import DomainError
    from tests.test_context_contract import revise_prompt
    from tests.test_generation_preparation import during_assembly
    run = complete(client, prepared(client, story))
    assert run['opportunity_id']
    during_assembly(monkeypatch, lambda: revise_prompt(client, 'scribe'))
    with pytest.raises(DomainError, match='while context was being assembled'):
        write(client, story)
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []


def test_retry_after_restart_uses_frozen_post_acceptance_inputs(client, story):
    from server.main import create_app
    from tests.test_profiles import MemoryVault
    run = prepared(client, story)
    client.app.state.assessment_runner.provider = AssessmentProvider(invalid=True)
    failed = complete(client, run)
    app = create_app(client.app.state.database.path)
    app.state.vault = MemoryVault()
    app.state.assessment_runner.provider = AssessmentProvider()
    service = Assessments(app.state.database)
    async def retry():
        app.state.assessment_runner.retry(run['jobs'][0]['id'])
        await app.state.assessment_runner.tasks[run['jobs'][0]['id']]
    asyncio.run(retry())
    restored = service.detail(run['id'])
    assert restored['opportunity_id'] and not restored['generation_id']
    assert restored['jobs'][0]['attempt'] == 2
    assert restored['jobs'][0]['snapshot']['content'] == failed['jobs'][0]['snapshot']['content']
