import asyncio
import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.assessment.context import parse_assessment
from server.assessment.models import AssessmentDecision
from server.assessment.service import Assessments
from server.assessment.writing import WritingRequests
from server.database import decode, one
from server.errors import DomainError
from server.generation_models import GenerateRequest
from server.providers.events import ProviderEvent
from tests.archive_legacy import remove_assessments
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_mechanics import configure, prepare
from tests.test_profiles import make_profile


def report(content, waiting=False):
    context = json.loads(content)
    node = context['context']['history'][-1]
    return {'summary': 'The exchange has reached a pause.', 'boundary_node_id': node['id'],
            'beat': {'label': 'A settled exchange', 'completed': True, 'waiting_for_player': waiting,
                     'protected': False, 'resolves_event': False, 'new_scene': False,
                     'family': 'narrative-push', 'attempt': None, 'extras': []},
            'evidence': [{'node_id': node['id'], 'quote': node['text']}]}


class AssessmentProvider:
    def __init__(self, waiting=False, invalid=False):
        self.calls, self.waiting, self.invalid = [], waiting, invalid

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        yield ProviderEvent(text='invalid' if self.invalid else json.dumps(report(content, self.waiting)), done=True)


def setup_assessment(client, story, **options):
    profile = make_profile(client, 'Primary assessor', primary=True)
    configure(client, story, automatic_assessment=True, chance=100, cooldown=0)
    append(client, story['branch_id'], 'The exchange is finished. The room falls quiet.', 0)
    client.app.state.assessment_runner.provider = AssessmentProvider(**options)
    client.app.state.runner.provider = DraftProvider()
    return profile


def start(client, story, **values):
    body = {'operation_id': uuid4().hex, 'expected_revision': 1, **values}
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def settled(client, run_id):
    for _ in range(100):
        run = client.get(f'/api/assessments/{run_id}').json()
        if all(job['status'] not in {'queued', 'running'} for job in run['jobs']):
            # Final dispatch follows job persistence in the runner.
            time.sleep(0.01)
            return client.get(f'/api/assessments/{run_id}').json()
        time.sleep(0.01)
    pytest.fail('Assessment did not finish within the bounded test wait.')


def test_automatic_assessment_freezes_one_roll_and_requires_prose_acceptance(client, story, monkeypatch):
    setup_assessment(client, story)
    run_id = start(client, story)['assessment_id']
    run = settled(client, run_id)
    generation = finished(client, run['generation_id'])
    assert len(client.app.state.assessment_runner.provider.calls) == 1
    assert run['jobs'][0]['snapshot']['profile']['name'] == 'Primary assessor'
    assert 'credential_ref' not in json.dumps(run)
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert len(branch['messages']) == 1 and branch['mechanics']['state']['beat'] == 0
    monkeypatch.setattr('server.assessment.context.secrets.token_hex', lambda *_: pytest.fail('Redraw'))
    repeated = start(client, story)
    second = finished(client, repeated['id'])
    assert generation['snapshot']['content'] == second['snapshot']['content']
    candidate = generation['candidates'][0]['id']
    assert client.post(f'/api/candidates/{candidate}/accept', json={'operation_id': uuid4().hex}).status_code == 200
    assert client.get(f"/api/branches/{story['branch_id']}").json()['mechanics']['state']['beat'] == 1


def test_waiting_for_player_never_draws_or_advances_cadence(client, story):
    setup_assessment(client, story, waiting=True)
    run = settled(client, start(client, story)['assessment_id'])
    opportunity = client.get(f"/api/opportunities/{run['opportunity_id']}").json()['snapshot']
    assert opportunity['draws'] == [] and opportunity['before'] == opportunity['after']
    assert run['generation_id'] and run['selected_job_id']


def test_comparison_waits_for_choice_and_freezes_inputs(client, story):
    first = setup_assessment(client, story)
    second = make_profile(client, 'Other assessor')
    run = settled(client, start(client, story, assessment_profile_ids=[first['profile_id'], second['profile_id']])['assessment_id'])
    assert not run['generation_id'] and not run['opportunity_id']
    assert run['jobs'][0]['snapshot']['content'] == run['jobs'][1]['snapshot']['content']
    body = {'operation_id': uuid4().hex, 'job_id': run['jobs'][1]['id']}
    response = client.post(f"/api/assessments/{run['id']}/decision", json=body)
    assert response.status_code == 200, response.text
    assert client.post(f"/api/assessments/{run['id']}/decision", json=body).json() == response.json()
    assert len(finished(client, response.json()['id'])['candidates']) == 1


def test_invalid_report_retry_preserves_inputs_and_attempts(client, story):
    setup_assessment(client, story, invalid=True)
    run = settled(client, start(client, story)['assessment_id'])
    job = run['jobs'][0]
    assert job['status'] == 'error' and not run['generation_id']
    client.app.state.assessment_runner.provider = AssessmentProvider()
    assert client.post(f"/api/assessment-jobs/{job['id']}/retry").status_code == 200
    after = settled(client, run['id'])
    assert after['snapshot'] == run['snapshot'] and after['jobs'][0]['snapshot'] == job['snapshot']
    assert after['generation_id']
    attempts = client.get(f"/api/assessment-jobs/{job['id']}/attempts").json()
    assert [attempt['status'] for attempt in attempts] == ['done', 'error']


def test_stop_prevents_auto_dispatch_and_stale_decision_rejects(client, story):
    setup_assessment(client, story)
    db = client.app.state.database
    request = GenerateRequest(operation_id=uuid4().hex, expected_revision=1)
    run_id = WritingRequests(db).create(story['branch_id'], request)['assessment_id']
    service = Assessments(db)
    job_id = service.pending(run_id)[0]['id']
    service.stop(run_id)
    asyncio.run(client.app.state.assessment_runner.run(job_id))
    run = service.detail(run_id)
    assert run['jobs'][0]['status'] == 'done' and not run['generation_id']
    append(client, story['branch_id'], 'The situation changed.', 1)
    with pytest.raises(DomainError, match='earlier Story'):
        service.decide(run_id, AssessmentDecision(operation_id=uuid4().hex, job_id=job_id))
    assert not service.detail(run_id)['generation_id']


@pytest.mark.parametrize('mode', ['disabled', 'skip', 'prepared', 'ooc', 'edit'])
def test_bypassed_requests_do_not_call_assessor(client, story, mode):
    setup_assessment(client, story)
    values = {}
    if mode == 'disabled':
        configure(client, story, enabled=False, automatic_assessment=True)
    if mode == 'skip':
        values['assess_beat'] = False
    if mode == 'prepared':
        prepare(client, story['branch_id'], revision=1)
    if mode == 'ooc':
        client.post(f"/api/branches/{story['branch_id']}/messages", json={'operation_id': uuid4().hex, 'expected_revision': 1, 'text': 'Pause.', 'role': 'ooc'})
        values['expected_revision'] = 2
    if mode == 'edit':
        node = client.get(f"/api/branches/{story['branch_id']}").json()['head_id']
        fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={'operation_id': uuid4().hex, 'expected_revision': 1, 'node_id': node, 'replacement': 'Edited.', 'name': 'Edited'}).json()
        story = {**story, 'branch_id': fork['branch_id']}
        values['expected_revision'] = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    assert 'id' in start(client, story, **values)
    assert client.app.state.assessment_runner.provider.calls == []


def test_report_rejects_missing_flags_and_fabricated_evidence(client, story):
    setup_assessment(client, story)
    run = settled(client, start(client, story)['assessment_id'])
    snapshot = run['jobs'][0]['snapshot']
    valid = report(snapshot['content'])
    for missing in ['completed', 'waiting_for_player', 'protected', 'resolves_event', 'new_scene']:
        invalid = deepcopy(valid)
        del invalid['beat'][missing]
        with pytest.raises(DomainError):
            parse_assessment(json.dumps(invalid), snapshot)
    valid['evidence'][0]['quote'] = 'An invented action.'
    with pytest.raises(DomainError, match='exactly'):
        parse_assessment(json.dumps(valid), snapshot)


def test_assessment_archive_preserves_seed_jobs_writer_and_rejects_tampering(client, story):
    setup_assessment(client, story)
    run = settled(client, start(client, story)['assessment_id'])
    finished(client, run['generation_id'])
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    restored = client.get(f"/api/assessments/{mapping[run['id']]}").json()
    assert restored['snapshot']['seed'] == run['snapshot']['seed']
    assert restored['jobs'][0]['snapshot']['content'] == run['jobs'][0]['snapshot']['content']
    assert restored['generation_id'] == mapping[run['generation_id']]
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    broken = deepcopy(document)
    frozen = decode(broken['data']['assessment_runs'][0]['snapshot'])
    frozen['seed'] = 'tampered'
    broken['data']['assessment_runs'][0]['snapshot'] = json.dumps(frozen)
    assert client.post('/api/archives/imports', json={'content': json.dumps(broken)}).status_code == 400
    with client.app.state.database.connect() as connection:
        assert one(connection, 'SELECT COUNT(*) AS n FROM assessment_runs')['n'] == 2


def test_explicit_bypass_stops_pending_assessment_dispatch(client, story):
    setup_assessment(client, story)
    database = client.app.state.database
    requests = WritingRequests(database)
    original = GenerateRequest(operation_id=uuid4().hex, expected_revision=1)
    run_id = requests.create(story['branch_id'], original)['assessment_id']
    bypass = GenerateRequest(operation_id=uuid4().hex, expected_revision=1, assess_beat=False)
    generation = requests.create(story['branch_id'], bypass)
    assert 'id' in generation
    job_id = Assessments(database).pending(run_id)[0]['id']
    asyncio.run(client.app.state.assessment_runner.run(job_id))
    run = Assessments(database).detail(run_id)
    assert run['stopped'] and not run['generation_id'] and not run['opportunity_id']


def test_restore_unselected_comparison_preserves_inputs_and_can_choose(client, story):
    first = setup_assessment(client, story)
    second = make_profile(client, 'Second assessor')
    run = settled(client, start(client, story, assessment_profile_ids=[first['profile_id'], second['profile_id']])['assessment_id'])
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    selected = mapping[run['jobs'][1]['id']]
    response = client.post(f"/api/assessments/{mapping[run['id']]}/decision", json={'operation_id': uuid4().hex, 'job_id': selected})
    assert response.status_code == 200, response.text
    generation = finished(client, response.json()['id'])
    assert decode(generation['snapshot']['content'])['history'] == decode(run['snapshot']['writer_snapshot']['content'])['history']
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})


def test_recovered_queued_assessment_requires_explicit_retry(client, story):
    setup_assessment(client, story)
    database = client.app.state.database
    request = GenerateRequest(operation_id=uuid4().hex, expected_revision=1)
    run_id = WritingRequests(database).create(story['branch_id'], request)['assessment_id']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    recovered = Assessments(database).detail(mapping[run_id])
    job = recovered['jobs'][0]
    assert job['status'] == 'interrupted' and client.app.state.assessment_runner.provider.calls == []
    assert client.post(f"/api/assessment-jobs/{job['id']}/retry").status_code == 200
    run = settled(client, recovered['id'])
    assert run['generation_id'] and run['jobs'][0]['snapshot'] == job['snapshot']
    assert not Assessments(database).detail(run_id)['generation_id']


def test_version_eight_archive_upgrades_without_enabling_assessment(client, story):
    _, document = backup(client, story)
    remove_assessments(document)
    document['version'] = 8
    document['data'].pop('library_imports', None)
    document['data'].pop('asset_import_origins', None)
    document['data'].pop('asset_sources', None)
    document.pop('library_drafts', None)
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 201, response.text
    _, mapping = restore(client, response.json())
    branch = client.get(f"/api/branches/{mapping[story['branch_id']]}").json()
    assert not branch['mechanics']['automatic_assessment']


def test_assessment_sources_are_read_only_and_redacted(client, story):
    from server.side_context import branch_sources
    setup_assessment(client, story)
    run = settled(client, start(client, story)['assessment_id'])
    with client.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        sources = branch_sources(connection, branch)
    content = ''.join(item['text'] for item in sources if item['id'].startswith(f"assessment:{run['id']}:"))
    assert 'no accepted Story events' in content and 'credential_ref' not in content
    assert run['jobs'][0]['output'] in json.loads(content)['jobs'][0]['output']
