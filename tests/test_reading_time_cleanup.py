import time
from uuid import uuid4

from tests.test_archives import backup, restore
from tests.test_cleanup import ORIGINAL, select, setting, setup, start, wait_cleanup
from tests.test_generations import finished


def settled(client, run):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        candidate = finished(client, run['id'])['candidates'][0]
        if not candidate['usage'].get('cleanup_pending'):
            return candidate
        time.sleep(0.01)
    raise AssertionError('Background cleanup did not settle')


def reading_setup(client, story, mode='wait', verified=True):
    provider = setup(client, story, mode=mode)
    provider.background_capability = lambda _: {'verified': verified}
    setting(client, story, timing='reading')
    return provider


def test_draft_is_usable_during_cleanup_and_late_result_cannot_change_acceptance(client, story):
    provider = reading_setup(client, story, mode='late')
    run, _ = start(client, story)
    candidate = wait_cleanup(client, run)
    assert candidate['status'] == 'done' and candidate['output'] == ORIGINAL
    assert candidate['activity']['finished_at']
    response = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex})
    assert response.status_code == 200
    candidate = settled(client, run)
    assert candidate['cleanup']['status'] == 'cancelled'
    assert candidate['cleanup']['selected'] == 'original'
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == ORIGINAL
    assert len(provider.calls) == 2


def test_completed_reading_cleanup_keeps_original_selected_until_author_chooses(client, story):
    provider = reading_setup(client, story)
    run, _ = start(client, story)
    wait_cleanup(client, run)
    provider.release = True
    candidate = settled(client, run)
    assert candidate['cleanup']['status'] == 'done'
    assert candidate['cleanup']['selected'] == 'original'
    assert candidate['cleanup']['cleaned'] != ORIGINAL
    assert candidate['usage']['timings']['draft_ready_seconds'] >= 0
    assert candidate['cleanup']['usage']['cleanup_seconds'] >= 0


def test_unverified_reading_cleanup_skips_inference_without_delaying_original(client, story):
    provider = reading_setup(client, story, verified=False)
    run, _ = start(client, story)
    candidate = settled(client, run)
    assert candidate['cleanup']['status'] == 'skipped'
    assert 'verified interruption' in candidate['cleanup']['error']
    assert candidate['status'] == 'done' and len(provider.calls) == 1


def test_disable_during_reading_cancels_only_cleanup(client, story):
    reading_setup(client, story, mode='late')
    run, _ = start(client, story)
    candidate = wait_cleanup(client, run)
    setting(client, story, enabled=False, timing='reading')
    current = settled(client, run)
    assert current['attempt'] == candidate['attempt']
    assert current['status'] == 'done' and current['cleanup']['selected'] == 'original'


def test_author_can_select_completed_cleanup_and_accept_that_exact_version(client, story):
    reading_setup(client, story, mode='valid')
    run, _ = start(client, story)
    candidate = settled(client, run)
    assert select(client, candidate, 'cleaned').status_code == 200
    accepted = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex})
    assert accepted.status_code == 200
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == candidate['cleanup']['cleaned']


def test_archive_restore_of_pending_reading_cleanup_has_no_phantom_work(client, story):
    reading_setup(client, story)
    run, _ = start(client, story)
    wait_cleanup(client, run)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    candidate = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]
    assert candidate['status'] == 'done' and not candidate['usage'].get('cleanup_pending')
    assert candidate['cleanup']['status'] == 'interrupted'
    saved = client.get(f"/api/branches/{mapping[story['branch_id']]}/cleanup").json()
    assert saved['timing'] == 'reading' and saved['enabled'] == 0


def test_new_turn_cancels_old_cleanup_but_replayed_receipt_does_not(client, story):
    reading_setup(client, story)
    first, body = start(client, story)
    wait_cleanup(client, first)
    assert client.post(f"/api/branches/{story['branch_id']}/generations", json=body).json() == first
    assert client.get(f"/api/generations/{first['id']}").json()['candidates'][0]['cleanup']['status'] == 'running'
    second, _ = start(client, story)
    assert settled(client, first)['cleanup']['status'] == 'cancelled'
    assert wait_cleanup(client, second)['status'] == 'done'
