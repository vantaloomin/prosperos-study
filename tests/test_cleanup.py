import asyncio
import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.cleanup.protocol import PROMPT, apply_output, flag_draft
from server.cleanup.runner import prepare, record
from server.database import decode
from server.errors import DomainError
from server.generation_models import GenerateRequest
from server.generations import Generations
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_generations import finished
from tests.test_history import append
from tests.test_profiles import make_profile

ORIGINAL = ('😀 Mara waited by the door at 8. She let out a breath. Rain struck the glass. '
            'She let out a breath. The letter lay unopened. She let out a breath.')
CHOICES = {'intentional': [], 'dismissed': []}


class CleanupProvider:
    def __init__(self, original=ORIGINAL, mode='valid'):
        self.original, self.mode = original, mode
        self.calls = []
        self.release = False

    async def generate(self, profile, prompt, content):
        self.calls.append((deepcopy(profile), prompt, content))
        if prompt != PROMPT:
            yield ProviderEvent(text=self.original)
            yield ProviderEvent(done=True, usage={'output_tokens': 30})
            return
        if self.mode in {'wait', 'late'}:
            try:
                while not self.release:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                if self.mode != 'late':
                    raise
        if self.mode == 'error':
            raise DomainError('Cleanup provider failed.', 502)
        content = json.loads(content)
        first = content['eligible_spans'][0]
        replacements = [{'start': first['start'], 'end': first['end'], 'text': 'She exhaled'}]
        if self.mode == 'outside':
            replacements[0]['start'] = 0
        raw = json.dumps({'replacements': replacements}) if self.mode != 'invalid' else 'Here is a new story.'
        yield ProviderEvent(text=raw)
        yield ProviderEvent(done=True, usage={'output_tokens': 12})


def setting(client, story, enabled=True, **overrides):
    path = f"/api/branches/{story['branch_id']}/cleanup"
    current = client.get(path).json()
    body = {'operation_id': uuid4().hex, 'expected_version': current['version'], 'enabled': enabled, **overrides}
    response = client.put(path, json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def start(client, story, choices=CHOICES, revision=0, **extra):
    body = {'operation_id': uuid4().hex, 'expected_revision': revision, 'cleanup_choices': choices, **extra}
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def setup(client, story, original=ORIGINAL, mode='valid', enabled=True):
    make_profile(client, 'Writer', primary=True)
    provider = CleanupProvider(original, mode)
    client.app.state.runner.provider = provider
    if enabled:
        setting(client, story)
    return provider


def wait_cleanup(client, run):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        candidate = client.get(f"/api/generations/{run['id']}").json()['candidates'][0]
        if candidate['cleanup'] and candidate['cleanup']['status'] == 'running':
            return candidate
        time.sleep(0.01)
    pytest.fail('Cleanup did not start')


def select(client, candidate, selected):
    return client.post(f"/api/candidates/{candidate['id']}/cleanup-selection", json={
        'operation_id': uuid4().hex, 'expected_attempt': candidate['attempt'],
        'original_sha256': candidate['cleanup']['snapshot']['original_sha256'], 'selected': selected})


def test_default_off_makes_only_writer_call_and_does_not_change_story(client, story):
    provider = setup(client, story, enabled=False)
    assert client.get(f"/api/branches/{story['branch_id']}/cleanup").json()['enabled'] == 0
    run, _ = start(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['output'] == ORIGINAL and candidate['cleanup'] is None
    assert len(provider.calls) == 1
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []


def test_one_cleanup_preserves_original_and_exact_inputs_with_restorable_choice(client, story):
    provider = setup(client, story)
    run, body = start(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    cleanup = candidate['cleanup']
    assert candidate['status'] == 'done' and candidate['output'] == ORIGINAL
    assert cleanup['status'] == 'done' and cleanup['selected'] == 'cleaned'
    assert cleanup['snapshot']['original'] == ORIGINAL
    assert cleanup['cleaned'] == ORIGINAL.replace('She let out a breath', 'She exhaled', 1)
    assert len(provider.calls) == 2 and provider.calls[0][0] == provider.calls[1][0]
    assert candidate['usage']['output_tokens'] == 30 and cleanup['usage']['output_tokens'] == 12
    assert client.post(f"/api/branches/{story['branch_id']}/generations", json=body).json() == run
    assert len(provider.calls) == 2
    assert select(client, candidate, 'original').status_code == 200
    assert select(client, candidate, 'cleaned').status_code == 200
    assert select(client, candidate, 'original').status_code == 200
    accepted = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex})
    assert accepted.status_code == 200
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == ORIGINAL
    assert select(client, candidate, 'cleaned').status_code == 409


def test_cleaned_acceptance_is_explicit_and_keeps_original_inspectable(client, story):
    setup(client, story)
    run, _ = start(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    response = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex})
    assert response.status_code == 200
    after = client.get(f"/api/generations/{run['id']}").json()['candidates'][0]
    assert after['cleanup']['stale'] is False
    assert after['output'] == ORIGINAL
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == candidate['cleanup']['cleaned']


@pytest.mark.parametrize('choices,original', [
    (CHOICES, 'A fresh sentence about an unopened door.'),
    ({'intentional': [{'id': 'a' * 64, 'phrase': 'let out a breath'}], 'dismissed': []}, ORIGINAL),
    ({'intentional': [], 'dismissed': [{'id': 'b' * 64, 'phrase': 'she let out a breath'}]}, ORIGINAL),
    (None, ORIGINAL),
])
def test_unflagged_or_protected_wording_has_no_cleanup_call(client, story, choices, original):
    provider = setup(client, story, original)
    run, _ = start(client, story, choices=choices)
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'done' and candidate['cleanup']['status'] == 'skipped'
    assert len(provider.calls) == 1 and candidate['output'] == original


@pytest.mark.parametrize('mode', ['error', 'invalid', 'outside'])
def test_cleanup_failure_never_discards_original_or_retries_model(client, story, mode):
    provider = setup(client, story, mode=mode)
    run, _ = start(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'done' and candidate['cleanup']['status'] == 'error'
    assert candidate['output'] == ORIGINAL and candidate['cleanup']['selected'] == 'original'
    assert len(provider.calls) == 2
    assert client.post(f"/api/candidates/{candidate['id']}/retry").status_code == 409
    assert client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex}).status_code == 200


@pytest.mark.parametrize('action', ['stop', 'off', 'path', 'draft'])
def test_inflight_cancellation_and_staleness_leave_original_usable(client, story, action):
    provider = setup(client, story, mode='late' if action in {'stop', 'off'} else 'wait')
    run, _ = start(client, story)
    pending = wait_cleanup(client, run)
    assert pending['status'] == 'cleaning' and pending['output'] == ORIGINAL
    if action == 'stop':
        assert client.post(f"/api/candidates/{pending['id']}/cancel").status_code == 200
    elif action == 'off':
        setting(client, story, False)
    elif action == 'path':
        append(client, story['branch_id'], 'The scene moves on.', 0)
    else:
        with client.app.state.database.connect(write=True) as connection:
            connection.execute("UPDATE candidates SET output='A changed draft.' WHERE id=?", (pending['id'],))
    provider.release = True
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'done'
    assert candidate['cleanup']['selected'] == 'original'
    assert candidate['cleanup']['status'] in {'cancelled', 'stale'}
    assert candidate['output'] == ('A changed draft.' if action == 'draft' else ORIGINAL)
    assert len(provider.calls) == 2


def test_completed_cleanup_cannot_be_applied_to_a_changed_path(client, story):
    setup(client, story)
    run, _ = start(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    append(client, story['branch_id'], 'A different continuation.', 0)
    response = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex, 'as_new_branch': True})
    assert response.status_code == 409
    assert select(client, candidate, 'cleaned').status_code == 409
    assert select(client, candidate, 'original').status_code == 200
    response = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex, 'as_new_branch': True})
    assert response.status_code == 200


def test_toggle_is_path_scoped_and_idempotent(client, story):
    setup(client, story, enabled=False)
    first, body = setting(client, story)
    assert client.put(f"/api/branches/{story['branch_id']}/cleanup", json=body).json() == first
    other = client.post('/api/stories', json={'title': 'Other path'}).json()
    assert client.get(f"/api/branches/{other['branch_id']}/cleanup").json()['enabled'] == 0
    conflict = {**body, 'operation_id': uuid4().hex, 'enabled': False}
    assert client.put(f"/api/branches/{story['branch_id']}/cleanup", json=conflict).status_code == 409
    setting(client, story, False)
    run, _ = start(client, story)
    assert finished(client, run['id'])['candidates'][0]['cleanup'] is None


@pytest.mark.parametrize('recorded', [False, True])
def test_restart_during_cleanup_recovers_complete_original_without_a_call(client, story, recorded):
    provider = setup(client, story)
    database = client.app.state.database
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=0, cleanup_choices=CHOICES)
    run = Generations(database).create(story['branch_id'], body)
    candidate_id = run['candidate_ids'][0]
    with database.connect(write=True) as connection:
        connection.execute("UPDATE candidates SET output=?,status='cleaning',attempt=1 WHERE id=?", (ORIGINAL, candidate_id))
        generation = decode(connection.execute('SELECT snapshot FROM generations WHERE id=?', (run['id'],)).fetchone()[0])
    if recorded:
        candidate, snapshot, reason = prepare(database, candidate_id, generation)
        record(database, candidate, snapshot, reason)
    client.app.state.runner.recover()
    candidate = Generations(database).detail(run['id'])['candidates'][0]
    assert candidate['status'] == 'done' and candidate['output'] == ORIGINAL
    assert not provider.calls
    if recorded:
        assert candidate['cleanup']['status'] == 'interrupted'
    assert client.post(f'/api/candidates/{candidate_id}/accept', json={'operation_id': uuid4().hex}).status_code == 200


def test_cleanup_survives_archive_restore_with_opt_in_reset(client, story):
    setup(client, story)
    run, _ = start(client, story)
    before = finished(client, run['id'])['candidates'][0]
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    after = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]
    assert after['output'] == before['output'] and after['cleanup']['cleaned'] == before['cleanup']['cleaned']
    assert after['cleanup']['snapshot']['content'] == before['cleanup']['snapshot']['content']
    assert after['cleanup']['snapshot']['branch']['id'] == mapping[story['branch_id']]
    assert client.get(f"/api/branches/{mapping[story['branch_id']]}/cleanup").json()['enabled'] == 0


def test_evidence_respects_existing_motif_sources_and_only_edits_flagged_spans():
    report = flag_draft([], 'draft:1', ORIGINAL, CHOICES)
    assert report['evidence']
    assert not flag_draft([], 'draft:1', ORIGINAL, CHOICES, ['She let out a breath.'])['evidence']
    evidence = report['evidence'][0]
    edited, changes = apply_output(json.dumps({'replacements': [{
        'start': evidence['start'], 'end': evidence['end'], 'text': 'She exhaled'}]}), ORIGINAL, report['evidence'])
    assert edited == ORIGINAL.replace(evidence['quote'], 'She exhaled', 1) and len(changes) == 1
    with pytest.raises(DomainError):
        apply_output(json.dumps({'replacements': [{**changes[0], 'text': 'She left. A new event.'}]}), ORIGINAL, report['evidence'])


def test_history_matches_require_draft_evidence_and_never_send_other_prose(client, story):
    provider = setup(client, story, original='She let out a breath. The letter was still sealed.')
    append(client, story['branch_id'], 'She let out a breath. The secret was locked away.', 0)
    append(client, story['branch_id'], 'She let out a breath. Night settled over town.', 1)
    run, _ = start(client, story, revision=2)
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['cleanup']['status'] == 'done' and len(provider.calls) == 2
    cleanup_input = json.loads(provider.calls[1][2])
    assert 'The secret was locked away.' not in provider.calls[1][2]
    assert set(cleanup_input) == {'draft', 'eligible_spans', 'writer_guidance'}
    provider.original = 'An entirely different wording unfolds.'
    second, _ = start(client, story, revision=2)
    assert finished(client, second['id'])['candidates'][0]['cleanup']['status'] == 'skipped'
    assert len(provider.calls) == 3


def test_pending_writer_uses_frozen_opt_in_and_fork_starts_off(client, story):
    from tests.test_generations import WaitingProvider
    setup(client, story)
    first = append(client, story['branch_id'], 'An opening.', 0)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 1, 'node_id': first, 'name': 'Sibling'}).json()
    assert client.get(f"/api/branches/{fork['branch_id']}/cleanup").json()['enabled'] == 0
    client.app.state.runner.provider = WaitingProvider()
    run, _ = start(client, story, revision=1)
    candidate_id = run['candidate_ids'][0]
    client.post(f'/api/candidates/{candidate_id}/cancel')
    finished(client, run['id'])
    setting(client, story, False)
    setting(client, story, True)
    provider = CleanupProvider()
    client.app.state.runner.provider = provider
    assert client.post(f'/api/candidates/{candidate_id}/retry').status_code == 200
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'done' and candidate['cleanup']['status'] == 'stale'
    assert len(provider.calls) == 1


def test_legacy_assessment_continuation_keeps_cleanup_policy(client, story):
    from tests.legacy_assessment import dispatch, legacy_create
    from tests.test_assessments import settled, setup_assessment
    setup_assessment(client, story)
    setting(client, story)
    provider = CleanupProvider()
    client.app.state.runner.provider = provider
    run = legacy_create(client.app.state.database, story['branch_id'], GenerateRequest(
        operation_id=uuid4().hex, expected_revision=1, cleanup_choices=CHOICES))
    dispatch(client, run)
    assessed = settled(client, run['assessment_id'])
    candidate = finished(client, assessed['generation_id'])['candidates'][0]
    assert candidate['cleanup']['status'] == 'done' and len(provider.calls) == 2
    assert len(client.app.state.assessment_runner.provider.calls) == 1


def test_comparison_has_at_most_one_cleanup_per_writer_candidate(client, story):
    provider = setup(client, story)
    second = make_profile(client, 'Other writer')
    profiles = client.get('/api/profiles').json()['profiles']
    first = next(profile for profile in profiles if profile['name'] == 'Writer')
    run, _ = start(client, story, profile_ids=[first['profile_id'], second['profile_id']])
    candidates = finished(client, run['id'])['candidates']
    assert len(candidates) == 2 and all(item['cleanup']['status'] == 'done' for item in candidates)
    assert len(provider.calls) == 4
    assert sum(prompt == PROMPT for _, prompt, _ in provider.calls) == 2


def test_new_author_motif_invalidates_pending_cleanup_without_changing_story(client, story):
    from tests.test_memory_controls import entry, evidence, save
    provider = setup(client, story, mode='wait')
    append(client, story['branch_id'], 'She let out a breath. Rain struck the window.', 0)
    run, _ = start(client, story, revision=1)
    wait_cleanup(client, run)
    save(client, story['branch_id'], [entry(evidence(client, story['branch_id']), kind='emphasis', stance='motif')])
    provider.release = True
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['cleanup']['status'] == 'stale' and candidate['cleanup']['selected'] == 'original'


def test_restoring_inflight_cleanup_keeps_original_ready_without_resending(client, story):
    provider = setup(client, story, mode='wait')
    run, _ = start(client, story)
    wait_cleanup(client, run)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]
    assert restored['status'] == 'done' and restored['output'] == ORIGINAL
    assert restored['cleanup']['status'] == 'interrupted'
    assert len(provider.calls) == 2
    provider.release = True
    finished(client, run['id'])


def test_replaying_a_setting_receipt_does_not_cancel_a_current_cleanup(client, story):
    provider = setup(client, story, mode='wait', enabled=False)
    _, body = setting(client, story)
    run, _ = start(client, story)
    pending = wait_cleanup(client, run)
    assert client.put(f"/api/branches/{story['branch_id']}/cleanup", json=body).status_code == 200
    current = client.get(f"/api/generations/{run['id']}").json()['candidates'][0]
    assert current['status'] == 'cleaning' and current['cleanup']['id'] == pending['cleanup']['id']
    provider.release = True
    assert finished(client, run['id'])['candidates'][0]['cleanup']['status'] == 'done'


def test_cleanup_check_failure_after_writer_completion_preserves_a_usable_original(client, story, monkeypatch):
    provider = setup(client, story)

    def failed(*_args):
        raise RuntimeError('A detector failure')

    monkeypatch.setattr('server.cleanup.runner.prepare', failed)
    run, _ = start(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'done' and candidate['output'] == ORIGINAL
    assert 'original draft is available' in candidate['error']
    assert len(provider.calls) == 1
    assert client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex}).status_code == 200


def test_history_budget_keeps_whole_recent_passages_and_numeric_wording_is_protected():
    from server.cleanup.runner import fit_history
    passages = [{'id': str(index), 'text': 'x' * 100_000} for index in range(2)]
    kept, limited = fit_history(passages, ORIGINAL)
    assert limited and [item['id'] for item in kept] == ['1']
    assert not flag_draft([], 'draft:1', 'Mara paid 10 coins. ' * 3, CHOICES)['evidence']


def test_cleanup_receives_frozen_author_direction_and_notes(client, story):
    provider = setup(client, story)
    note = 'Keep her clipped voice and deliberate echoes; do not decide her next action.'
    response = client.post(f"/api/branches/{story['branch_id']}/messages", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'text': note, 'role': 'ooc'})
    assert response.status_code == 201
    run, _ = start(client, story, revision=1, direction='Preserve the quiet rhythm.')
    candidate = finished(client, run['id'])['candidates'][0]
    guidance = json.loads(provider.calls[1][2])['writer_guidance']
    assert guidance['author_notes'] == [note] and guidance['direction'] == 'Preserve the quiet rhythm.'
    assert guidance['role_instructions'] == provider.calls[0][1]
    assert candidate['cleanup']['snapshot']['guidance'] == guidance
