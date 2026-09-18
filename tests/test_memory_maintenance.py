import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.main import create_app
from tests.archive_legacy import remove_maintenance
from tests.prompt_fixtures import saved_prompt
from tests.test_archives import backup, restore
from tests.test_memory import small_profile
from tests.test_profiles import make_profile
from tests.test_story_summaries import TEXT, SummaryProvider, fork, publication, setup, started


def configure(client, story_id, enabled=True, batch_size=2, max_batches=1):
    story = client.get('/api/stories/' + story_id).json()
    memory = {**story['settings']['memory'], 'maintenance': {'enabled': enabled, 'batch_size': batch_size, 'max_batches': max_batches}}
    response = client.put('/api/stories/' + story_id, json={'title': story['title'], 'premise': story['premise'],
        'expected_revision': story['revision'], 'settings': {**story['settings'], 'memory': memory}})
    assert response.status_code == 200, response.text


def append(client, branch_id, text, role='narrator'):
    branch = client.get('/api/branches/' + branch_id).json()
    response = client.post('/api/branches/' + branch_id + '/messages', json={'operation_id': uuid4().hex,
        'expected_revision': branch['revision'], 'text': text, 'role': role})
    assert response.status_code == 201, response.text
    return response.json()['node_id']


def preview(client, branch_id, **options):
    branch = client.get('/api/branches/' + branch_id).json()
    body = {'expected_revision': branch['revision'], 'batch_size': 2, 'max_batches': 2, **options}
    response = client.post('/api/branches/' + branch_id + '/summary-backfill-preview', json=body)
    assert response.status_code == 200, response.text
    return body, response.json()


def start(client, branch_id, body, prepared):
    request = {**body, 'operation_id': uuid4().hex, 'preview_hash': prepared['preview_hash']}
    response = client.post('/api/branches/' + branch_id + '/summary-backfill', json=request)
    assert response.status_code == 201, response.text
    assert client.post('/api/branches/' + branch_id + '/summary-backfill', json=request).json() == response.json()
    return response.json()['id']


async def wait_status(client, batch_id, statuses=('done', 'error', 'paused', 'cancelled', 'interrupted')):
    for _ in range(1000):
        with client.app.state.database.connect() as connection:
            row = connection.execute('SELECT status FROM summary_batches WHERE id=?', (batch_id,)).fetchone()
            if row and row['status'] in statuses:
                return row['status']
        await asyncio.sleep(.01)
    raise AssertionError('Maintenance did not reach the expected state')


def finished(client, batch_id):
    assert client.portal.call(wait_status, client, batch_id) == 'done'
    return client.get('/api/summary-batches/' + batch_id).json()


async def wait_batches(client, branch_id, count):
    for _ in range(1000):
        with client.app.state.database.connect() as connection:
            rows = connection.execute('SELECT id FROM summary_batches WHERE branch_id=? ORDER BY rowid', (branch_id,)).fetchall()
        if len(rows) >= count:
            return rows[-1]['id']
        await asyncio.sleep(.01)
    raise AssertionError('Expected automatic batch was not queued')


def test_enabling_only_queues_new_prose_coalesces_updates_and_caps_each_wake(client):
    story, _ = setup(client)
    runner = client.app.state.maintenance_runner
    client.portal.call(runner.shutdown)
    runner.debounce_seconds = 0
    branch_id = story['branch_id']
    configure(client, story['story_id'])
    append(client, branch_id, 'Private instructions.', 'ooc')
    assert client.get('/api/branches/' + branch_id + '/summary-maintenance').json()['wakeup'] is None
    first = append(client, branch_id, 'The first new event.')
    second = append(client, branch_id, 'The second new event.')
    long_id = append(client, branch_id, 'A long accepted chapter with many exact ranges. ' * 600)
    before = client.get('/api/branches/' + branch_id).json()
    status = client.get('/api/branches/' + branch_id + '/summary-maintenance').json()
    assert status['waiting_contributions'] == 3 and status['wakeup']['allowance'] == 1
    client.portal.call(runner.start)
    batch_id = client.portal.call(wait_batches, client, branch_id, 1)
    batch = finished(client, batch_id)
    assert batch['kind'] == 'automatic' and len(batch['requests']) == 1
    calls = client.app.state.summary_runner.provider.calls
    sources = decode(calls[0][2])['sources']
    assert [source['node_id'] for source in sources] == [first, second]
    assert all(source['text'] != TEXT for source in sources)
    assert client.get('/api/branches/' + branch_id).json() == before
    status = client.get('/api/branches/' + branch_id + '/summary-maintenance').json()
    assert status['waiting_contributions'] == 1 and status['wakeup']['status'] == 'limited'
    client.portal.call(asyncio.sleep, .4)
    assert len(calls) == 1
    for expected_count in (2, 3):
        status = client.get('/api/branches/' + branch_id + '/summary-maintenance').json()
        response = client.post('/api/branches/' + branch_id + '/summary-maintenance/resume', json={
            'operation_id': uuid4().hex, 'expected_revision': status['wakeup']['revision']})
        assert response.status_code == 200, response.text
        next_batch = client.portal.call(wait_batches, client, branch_id, expected_count)
        finished(client, next_batch)
    long_sources = [source for call in calls[1:] for source in decode(call[2])['sources']]
    assert all(source['node_id'] == long_id for source in long_sources)
    assert len({(source['start'], source['end']) for source in long_sources}) == 4
    assert long_sources[2]['start'] == long_sources[1]['end']
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM summary_versions').fetchone()[0] == 0


def test_backfill_compares_with_hard_limits_and_skips_requested_exclusions(client):
    story, first = setup(client)
    branch_id = story['branch_id']
    run = started(client, branch_id)
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, branch_id, enabled=False)).status_code == 201
    append(client, branch_id, 'A second large chapter. ' * 1000)
    alternate = make_profile(client, 'Backfill alternate')
    body, prepared = preview(client, branch_id, max_batches=3, profile_ids=[first['profile_id'], alternate['profile_id']])
    assert prepared['batch_count'] == 3 and prepared['request_count'] == 6
    assert prepared['covered_count'] == 1 and prepared['selected_count'] == 6
    assert len(client.app.state.summary_runner.provider.calls) == 1
    batch = finished(client, start(client, branch_id, body, prepared))
    calls = client.app.state.summary_runner.provider.calls[1:]
    assert len(calls) == 6
    for offset in (0, 2, 4):
        assert calls[offset][1:] == calls[offset + 1][1:]
        assert all(source['text'] != TEXT for source in decode(calls[offset][2])['sources'])
    assert len(batch['runs']) == 3
    _, remaining = preview(client, branch_id)
    assert remaining['covered_count'] == 7


def test_backfill_adapts_batch_size_to_smallest_profile_without_losing_remaining_ranges(client):
    story, primary = setup(client)
    append(client, story['branch_id'], 'A long passage continues through several sections. ' * 1000)
    smaller = small_profile(client, 'Small context', limit=4096)
    _, prepared = preview(client, story['branch_id'], batch_size=8, max_batches=4,
                          profile_ids=[primary['profile_id'], smaller['profile_id']])
    assert prepared['eligible_count'] > prepared['selected_count']
    assert prepared['batch_count'] == 4 and prepared['request_count'] == 8
    assert all(batch['source_count'] < 8 for batch in prepared['batches'])
    assert all(job['estimated_input_tokens'] <= 3584 for batch in prepared['batches'] for job in batch['jobs'])
    assert not client.app.state.summary_runner.provider.calls


def test_stop_and_explicit_resume_preserve_attempts_and_frozen_inputs(client):
    story, _ = setup(client)
    append(client, story['branch_id'], 'A later chapter unfolds. ' * 500)
    provider = client.app.state.summary_runner.provider
    provider.wait = True
    body, prepared = preview(client, story['branch_id'], batch_size=1, max_batches=3)
    batch_id = start(client, story['branch_id'], body, prepared)
    client.portal.call(wait_status, client, batch_id, ('running',))
    client.portal.call(asyncio.sleep, .05)
    assert client.post('/api/summary-batches/' + batch_id + '/stop').status_code == 200
    from tests.test_story_summaries import settle
    client.portal.call(settle, client)
    stopped = client.get('/api/summary-batches/' + batch_id).json()
    assert stopped['status'] == 'cancelled' and len(provider.calls) == 1
    first_call = provider.calls[0]
    prompt = saved_prompt(client, 'memory-summary')
    assert client.put('/api/prompts/memory-summary', json={'expected_version_id': prompt['id'], 'template': 'Later instructions'}).status_code == 200
    provider.wait = False
    request = {'operation_id': uuid4().hex, 'expected_status': 'cancelled'}
    response = client.post('/api/summary-batches/' + batch_id + '/resume', json=request)
    assert response.status_code == 200, response.text
    assert client.post('/api/summary-batches/' + batch_id + '/resume', json=request).json() == response.json()
    done = finished(client, batch_id)
    assert len(provider.calls) == 4 and provider.calls[1] == first_call
    attempts = client.get('/api/summary-jobs/' + done['requests'][0]['id'] + '/attempts').json()
    assert any(attempt['output'] == '{"items":[' and attempt['status'] == 'cancelled' for attempt in attempts)


def test_failure_stops_following_calls_and_disabled_prompt_pauses_dispatch(client):
    story, _ = setup(client)
    append(client, story['branch_id'], 'Enough accepted prose for another excerpt. ' * 400)
    provider = client.app.state.summary_runner.provider
    provider.fail = True
    body, prepared = preview(client, story['branch_id'], batch_size=1, max_batches=3)
    batch_id = start(client, story['branch_id'], body, prepared)
    assert client.portal.call(wait_status, client, batch_id) == 'error'
    client.portal.call(asyncio.sleep, .4)
    assert len(provider.calls) == 1
    prompt = saved_prompt(client, 'memory-summary')
    assert client.put('/api/prompts/memory-summary/activation', json={'enabled': False, 'expected_revision': prompt['activation_revision']}).status_code == 200
    assert client.post('/api/summary-batches/' + batch_id + '/resume', json={'operation_id': uuid4().hex, 'expected_status': 'error'}).status_code == 409


def test_stale_backfill_cannot_duplicate_a_new_manual_request(client):
    story, _ = setup(client)
    body, prepared = preview(client, story['branch_id'])
    started(client, story['branch_id'])
    response = client.post('/api/branches/' + story['branch_id'] + '/summary-backfill', json={**body,
        'operation_id': uuid4().hex, 'preview_hash': prepared['preview_hash']})
    assert response.status_code == 409
    assert client.get('/api/branches/' + story['branch_id'] + '/summary-batches').json() == []
    assert len(client.app.state.summary_runner.provider.calls) == 1


def test_edited_fork_queues_only_replacement_and_plain_fork_queues_nothing(client):
    story, _ = setup(client)
    client.portal.call(client.app.state.maintenance_runner.shutdown)
    configure(client, story['story_id'])
    branch = client.get('/api/branches/' + story['branch_id']).json()
    plain = fork(client, branch['id'], branch['head_id'])
    edited = fork(client, branch['id'], branch['head_id'], 'An edited opening with different evidence.')
    assert client.get('/api/branches/' + plain + '/summary-maintenance').json()['waiting_contributions'] == 0
    assert client.get('/api/branches/' + edited + '/summary-maintenance').json()['waiting_contributions'] == 1
    assert client.get('/api/branches/' + branch['id'] + '/summary-maintenance').json()['waiting_contributions'] == 0


def test_restore_keeps_queued_work_interrupted_and_preserves_exact_inputs(client):
    story, _ = setup(client)
    runner = client.app.state.maintenance_runner
    client.portal.call(runner.shutdown)
    configure(client, story['story_id'])
    append(client, story['branch_id'], 'A new accepted event.')
    body, prepared = preview(client, story['branch_id'])
    batch_id = start(client, story['branch_id'], body, prepared)
    original = client.get('/api/summary-batches/' + batch_id).json()
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = client.get('/api/summary-batches/' + mapping[batch_id]).json()
    assert copied['status'] == 'interrupted' and all(item['status'] == 'interrupted' for item in copied['requests'])
    status = client.get('/api/branches/' + mapping[story['branch_id']] + '/summary-maintenance').json()
    assert status['wakeup']['status'] == 'interrupted'
    first_run = original['runs'][0]['run_id']
    before = client.get('/api/summaries/' + first_run, params={'branch_id': story['branch_id']}).json()
    after = client.get('/api/summaries/' + mapping[first_run], params={'branch_id': mapping[story['branch_id']]}).json()
    assert after['jobs'][0]['snapshot']['content'] == before['jobs'][0]['snapshot']['content']
    assert client.post('/api/summary-batches/' + batch_id + '/stop').status_code == 200
    configure(client, story['story_id'], False)
    client.portal.call(runner.start)
    client.portal.call(asyncio.sleep, .5)
    assert not client.app.state.summary_runner.provider.calls
    request = {'operation_id': uuid4().hex, 'expected_status': 'interrupted'}
    assert client.post('/api/summary-batches/' + mapping[batch_id] + '/resume', json=request).status_code == 200
    finished(client, mapping[batch_id])
    second_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second_file)


@pytest.mark.parametrize('kind', ['count', 'status', 'order', 'source'])
def test_archives_reject_invalid_maintenance_ledgers(client, kind):
    story, _ = setup(client)
    client.portal.call(client.app.state.maintenance_runner.shutdown)
    configure(client, story['story_id'])
    append(client, story['branch_id'], 'Another event.')
    body, prepared = preview(client, story['branch_id'])
    start(client, story['branch_id'], body, prepared)
    _, document = backup(client, story)
    data = document['data']
    if kind == 'count':
        snapshot = decode(data['summary_batches'][0]['snapshot'])
        snapshot['request_count'] += 1
        data['summary_batches'][0]['snapshot'] = encode(snapshot)
    elif kind == 'status':
        data['summary_batches'][0]['status'] = 'done'
    elif kind == 'order':
        data['summary_batch_runs'][0]['ordinal'] = 5
    else:
        data['summary_pending'][0]['node_id'] = 'outside-this-story'
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_version_21_upgrade_adds_empty_queues_without_turning_on_maintenance(client):
    story, _ = setup(client)
    _, document = backup(client, story)
    remove_maintenance(document)
    document['version'] = 21
    original = deepcopy(document)
    upgraded = parse_archive(encode(document))
    assert upgraded['version'] == ARCHIVE_VERSION and upgraded['data']['summary_batches'] == []
    assert original == document
    assert not decode(upgraded['data']['stories'][0]['settings'])['memory']['maintenance']['enabled']


class GatedSummaryProvider(SummaryProvider):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, profile, prompt, content):
        async for event in super().generate(profile, prompt, content):
            if len(self.calls) == 1:
                self.started.set()
                await self.release.wait()
            yield event


def test_disabling_prompt_during_a_batch_pauses_before_the_next_provider_call(client):
    story, _ = setup(client)
    append(client, story['branch_id'], 'A long chapter provides later evidence. ' * 500)
    provider = GatedSummaryProvider()
    client.app.state.summary_runner.provider = provider
    body, prepared = preview(client, story['branch_id'], batch_size=1, max_batches=3)
    batch_id = start(client, story['branch_id'], body, prepared)
    client.portal.call(asyncio.wait_for, provider.started.wait(), 5)
    prompt = saved_prompt(client, 'memory-summary')
    response = client.put('/api/prompts/memory-summary/activation', json={
        'enabled': False, 'expected_revision': prompt['activation_revision']})
    assert response.status_code == 200
    client.portal.call(provider.release.set)
    assert client.portal.call(wait_status, client, batch_id) == 'paused'
    batch = client.get('/api/summary-batches/' + batch_id).json()
    assert [job['status'] for job in batch['requests']] == ['done', 'queued', 'queued']
    assert len(provider.calls) == 1
    prompt = saved_prompt(client, 'memory-summary')
    assert client.put('/api/prompts/memory-summary/activation', json={
        'enabled': True, 'expected_revision': prompt['activation_revision']}).status_code == 200
    response = client.post('/api/summary-batches/' + batch_id + '/resume', json={
        'operation_id': uuid4().hex, 'expected_status': 'paused'})
    assert response.status_code == 200, response.text
    finished(client, batch_id)
    assert len(provider.calls) == 3


def test_fresh_app_recovery_holds_old_queues_until_explicit_resume(tmp_path):
    path = tmp_path / 'restart.sqlite3'
    headers = {'x-roleplay-client': 'workspace'}
    with TestClient(create_app(path), headers=headers) as original:
        story, _ = setup(original)
        original.portal.call(original.app.state.maintenance_runner.shutdown)
        configure(original, story['story_id'])
        append(original, story['branch_id'], 'New accepted evidence before shutdown.')
        body, prepared = preview(original, story['branch_id'])
        batch_id = start(original, story['branch_id'], body, prepared)
        assert not original.app.state.summary_runner.provider.calls
    app = create_app(path)
    provider = SummaryProvider()
    app.state.summary_runner.provider = provider
    app.state.maintenance_runner.debounce_seconds = 0
    with TestClient(app, headers=headers) as restarted:
        restarted.portal.call(asyncio.sleep, .4)
        batch = restarted.get('/api/summary-batches/' + batch_id).json()
        status = restarted.get('/api/branches/' + story['branch_id'] + '/summary-maintenance').json()
        assert batch['status'] == status['wakeup']['status'] == 'interrupted'
        assert all(job['status'] == 'interrupted' for job in batch['requests'])
        assert not provider.calls
        response = restarted.post('/api/summary-batches/' + batch_id + '/resume', json={
            'operation_id': uuid4().hex, 'expected_status': 'interrupted'})
        assert response.status_code == 200, response.text
        finished(restarted, batch_id)
        assert len(provider.calls) == 1
        assert provider.calls[0][2] == prepared['batches'][0]['jobs'][0]['content']
