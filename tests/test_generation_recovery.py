from copy import deepcopy
from uuid import uuid4

from server.archives.format import ARCHIVE_VERSION
from server.archives.migrations import upgrade
from tests.archive_legacy import remove_v062_prompts
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, WaitingProvider, finished, generate
from tests.test_profiles import make_profile


def test_lost_save_and_generation_receipts_recover_without_duplicate_work(client, story):
    branch = story['branch_id']
    save = {'operation_id': uuid4().hex, 'expected_revision': 0, 'role': 'narrator', 'text': 'A saved passage.'}
    assert client.get(f"/api/operations/{save['operation_id']}").json()['result'] is None
    saved = client.post(f'/api/branches/{branch}/messages', json=save).json()
    assert client.get(f"/api/operations/{save['operation_id']}").json() == {'kind': 'message', 'result': saved}
    assert client.post(f'/api/branches/{branch}/messages', json=save).json() == saved
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    make_profile(client, 'Writer', primary=True)
    request = {'operation_id': f"continue-{saved['node_id']}", 'expected_revision': 1}
    run = client.post(f'/api/branches/{branch}/generations', json=request).json()
    finished(client, run['id'])
    assert client.get(f"/api/operations/{request['operation_id']}").json() == {'kind': 'generate', 'result': run}
    assert client.post(f'/api/branches/{branch}/generations', json=request).json() == run
    assert len(provider.calls) == 1
    assert len(client.get(f'/api/branches/{branch}').json()['messages']) == 1


def test_attempt_timing_retry_receipt_and_terminal_cancel(client, story):
    client.app.state.runner.provider = WaitingProvider()
    make_profile(client, 'Writer', primary=True)
    run = generate(client, story)
    candidate_id = run['candidate_ids'][0]
    current = client.get(f"/api/generations/{run['id']}").json()['candidates'][0]
    assert current['activity']['started_at'] <= current['activity']['first_text_at']
    assert current['activity']['finished_at'] is None
    client.post(f'/api/candidates/{candidate_id}/cancel')
    stopped = finished(client, run['id'])['candidates'][0]
    assert stopped['activity']['error_kind'] == 'cancelled'
    assert stopped['activity']['finished_at'] >= stopped['activity']['last_event_at']
    retry = {'operation_id': uuid4().hex, 'expected_attempt': 1}
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    assert client.post(f'/api/candidates/{candidate_id}/retry', json=retry).status_code == 200
    done = finished(client, run['id'])['candidates'][0]
    assert done['attempt'] == 2 and done['activity']['attempt'] == 2
    assert client.post(f'/api/candidates/{candidate_id}/retry', json=retry).status_code == 200
    assert len(provider.calls) == 1
    assert client.post(f'/api/candidates/{candidate_id}/cancel').json() == {'stopped': False, 'status': 'done'}
    assert client.get(f"/api/generations/{run['id']}").json()['candidates'][0] == done
    summary = client.get(f"/api/branches/{story['branch_id']}/generations").json()[0]
    assert summary['statuses'] == ['done'] and summary['unaccepted']
    assert 'snapshot' not in summary and 'output' not in summary


def test_activity_archive_round_trip_and_v30_migration(client, story):
    client.app.state.runner.provider = DraftProvider()
    make_profile(client, 'Writer', primary=True)
    run = generate(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]
    assert restored['activity'] == {**candidate['activity'], 'candidate_id': mapping[candidate['id']]}
    legacy = deepcopy(document)
    legacy['version'] = 30
    remove_v062_prompts(legacy)
    del legacy['data']['candidate_activity']
    del legacy['data']['path_revisions']
    upgraded = upgrade(legacy)
    assert upgraded['version'] == ARCHIVE_VERSION and upgraded['data']['candidate_activity'] == []
