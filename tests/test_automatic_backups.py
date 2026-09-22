import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.service import Archives
from server.backups import files, storage
from server.backups.models import BackupNow
from server.database import one
from server.main import create_app
from tests.test_archive_recovery import saved_work
from tests.test_archives import backup, restore
from tests.test_artwork import png
from tests.test_history import append
from tests.test_library import create_book, publish, with_book
from tests.test_library_imports import publish_import, stage
from tests.test_v07_manuscript import book_fixture

HEADERS = {'x-roleplay-client': 'workspace'}


def configure(client, **changes):
    current = client.get('/api/backups/settings').json()
    body = {key: current[key] for key in ('enabled', 'interval_minutes', 'keep_count', 'destination', 'include_sidebar')}
    body.update(expected_revision=current['revision'], **changes)
    response = client.put('/api/backups/settings', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def run_now(client):
    response = client.post('/api/backups', json={'operation_id': uuid4().hex,
                           'expected_revision': client.get('/api/backups/settings').json()['revision']})
    assert response.status_code == 201, response.text
    return response.json()


def scheduled(client):
    service = client.app.state.backups
    return service.run(timestamp=service.settings()['next_run_at'])


def test_off_by_default_settings_validation_and_conflicts(client):
    settings = client.get('/api/backups/settings').json()
    assert not settings['enabled'] and settings['next_run_at'] is None
    assert client.app.state.backups.run() is None
    assert client.get('/api/backups').json() == []
    updated = configure(client, enabled=True, interval_minutes=15, keep_count=2)
    assert updated['revision'] == 1 and updated['next_run_at']
    assert client.put('/api/backups/settings', json={'expected_revision': 0}).status_code == 409
    for values in ({'interval_minutes': 0}, {'keep_count': 0}, {'destination': '../outside'}):
        assert client.put('/api/backups/settings', json={'expected_revision': 1, **values}).status_code == 422
    assert not configure(client, enabled=False)['next_run_at']
    assert client.app.state.backups.run(timestamp='2099-01-01T00:00:00+00:00') is None


def test_due_time_and_one_catchup_copy(client, story):
    configure(client, enabled=True, interval_minutes=15)
    service = client.app.state.backups
    assert service.run() is None
    future = '2099-01-01T00:00:00+00:00'
    run = service.run(timestamp=future)
    assert run['status'] == 'ready' and run['trigger'] == 'scheduled'
    assert service.run(timestamp=future) is None
    assert service.settings()['next_run_at'] == '2099-01-01T00:15:00+00:00'
    assert len(client.get('/api/backups').json()) == 1


def test_retention_preserves_manual_archives_manual_copies_and_unrelated_files(client, story):
    configure(client, enabled=True, keep_count=1)
    manual_archive, _ = backup(client)
    manual_copy = run_now(client)
    first = scheduled(client)
    unrelated = Path(first['directory']) / 'keep-me.json'
    unrelated.write_text('author-owned file', encoding='utf-8')
    append(client, story['branch_id'], 'A later revision.', 0)
    second = scheduled(client)
    assert second['status'] == 'ready'
    assert client.app.state.backups.get(first['id'])['status'] == 'pruned'
    assert not files.run_path(first).exists()
    assert files.run_path(second).exists() and files.run_path(manual_copy).exists()
    assert unrelated.read_text(encoding='utf-8') == 'author-owned file'
    assert client.get(manual_archive['download_url']).status_code == 200


def test_destinations_are_isolated_and_missing_destination_is_a_durable_failure(client, story, tmp_path):
    configure(client, enabled=True, keep_count=1)
    original = scheduled(client)
    custom = tmp_path / 'second destination'
    custom.mkdir()
    configure(client, destination=str(custom))
    moved = scheduled(client)
    assert Path(moved['directory']).parent == custom and files.run_path(original).exists()
    configure(client, destination=str(tmp_path / 'unmounted'))
    failed = scheduled(client)
    assert failed['status'] == 'error' and 'unavailable' in failed['error']
    assert files.run_path(original).exists() and files.run_path(moved).exists()
    assert not (tmp_path / 'unmounted').exists()
    configure(client, destination=str(custom))
    recovered = scheduled(client)
    assert recovered['status'] == 'ready' and not files.run_path(moved).exists()


def test_failed_write_keeps_last_good_copy_and_no_partial_is_recoverable(client, story, monkeypatch):
    configure(client, enabled=True, keep_count=1)
    good = scheduled(client)

    def fail_flush(_descriptor):
        raise OSError('fixture disk is full')

    monkeypatch.setattr(files.os, 'fsync', fail_flush)
    failed = scheduled(client)
    assert failed['status'] == 'error' and 'free space' in failed['error']
    assert files.run_path(good).exists() and not files.run_path(failed).exists()
    assert not files.run_path(failed).with_suffix('.partial').exists()
    assert client.post(f"/api/backups/{failed['id']}/review", json={}).status_code == 409


def test_changed_backup_is_not_deleted_or_restored(client, story):
    configure(client, enabled=True, keep_count=1)
    first = scheduled(client)
    files.run_path(first).write_text('replaced content', encoding='utf-8')
    assert client.post(f"/api/backups/{first['id']}/review", json={}).status_code == 409
    newest = scheduled(client)
    assert newest['status'] == 'ready' and 'could not be removed' in newest['error']
    assert files.run_path(first).read_text(encoding='utf-8') == 'replaced content'
    assert client.app.state.backups.get(first['id'])['status'] == 'ready'


def test_manual_run_retries_are_idempotent_and_settings_are_frozen(client, story):
    body = {'operation_id': uuid4().hex, 'expected_revision': 0}
    response = client.post('/api/backups', json=body)
    assert response.status_code == 201, response.text
    first = response.json()
    configure(client, include_sidebar=True)
    assert client.post('/api/backups', json=body).json() == first
    assert not first['settings']['include_sidebar']
    assert client.post('/api/backups', json={**body, 'expected_revision': 1}).status_code == 409
    assert client.post('/api/backups', json={'operation_id': uuid4().hex, 'expected_revision': 0}).status_code == 409
    assert len(client.get('/api/backups').json()) == 1


def test_concurrent_triggers_only_create_one_copy(client, story, monkeypatch):
    service = client.app.state.backups
    entered, release = Event(), Event()
    original = Archives.build

    def delayed(self, body):
        entered.set()
        assert release.wait(10)
        return original(self, body)

    monkeypatch.setattr(Archives, 'build', delayed)
    request = BackupNow(operation_id=uuid4().hex, expected_revision=0)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.run, request)
        try:
            assert entered.wait(10)
            assert service.run(request)['status'] == 'running'
            assert service.run() is None
            response = client.post('/api/backups', json={'operation_id': uuid4().hex, 'expected_revision': 0})
            assert response.status_code == 409
        finally:
            release.set()
        assert future.result()['status'] == 'ready'
    assert len(client.get('/api/backups').json()) == 1


def test_review_reuses_verified_archive_and_restore_preserves_book_and_original_path(client, story):
    book_fixture(client, story)
    run = run_now(client)
    first = client.post(f"/api/backups/{run['id']}/review", json={})
    assert first.status_code == 200, first.text
    archive = first.json()
    assert client.post(f"/api/backups/{run['id']}/review", json={}).json() == archive
    assert len(client.get('/api/archives').json()) == 1
    append(client, story['branch_id'], 'Written after the copy.', 4)
    _, mapping = restore(client, archive)
    copied = client.get(f"/api/branches/{mapping[story['branch_id']]}").json()
    original = client.get(f"/api/branches/{story['branch_id']}").json()
    assert 'Written after the copy.' not in str(copied) and 'Written after the copy.' in str(original)
    assert len(copied['messages']) == 4 and len(original['messages']) == 5
    restored_book = client.get(f"/api/stories/{mapping[story['story_id']]}/manuscript").json()['document']
    assert [item['title'] for item in restored_book['chapters']] == ['Arrival', 'Departure']
    assert restored_book['chapters'][0]['scenes'][0]['branch_id'] == mapping[story['branch_id']]
    files.run_path(run).write_text('tampered after review', encoding='utf-8')
    assert client.post(f"/api/backups/{run['id']}/review", json={}).status_code == 409
    # The separately staged recovery copy still has its own checked integrity.
    assert client.get(archive['download_url']).status_code == 200


def test_fresh_workspace_restore_preserves_saved_requests_library_and_private_choice(client, tmp_path):
    book = create_book(client)
    story = with_book(client, book, 'Protected work')
    publish(client, book)
    _, generation, _, conversation = saved_work(client, story)
    without = run_now(client)
    assert not json.loads(files.read_archive(without))['data']['side_threads']
    configure(client, enabled=True, include_sidebar=True)
    run = scheduled(client)
    document = json.loads(files.read_archive(run))
    assert document['data']['side_threads']
    assert 'backup_settings' not in document['data'] and 'backup_runs' not in document['data']
    assert all(row['credential_ref'] is None for row in document['data']['profile_versions'])
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers=HEADERS) as target:
        staged = target.post('/api/archives/imports', json={'content': files.read_archive(run)}).json()
        _, mapping = restore(target, staged)
        restored = target.get('/api/generations/' + mapping[generation['id']]).json()
        original = client.get('/api/generations/' + generation['id']).json()
        assert restored['snapshot']['content'] == original['snapshot']['content']
        assert restored['candidates'][0]['output'] == original['candidates'][0]['output']
        assert len(target.get(f"/api/library/{mapping[book['asset_id']]}/versions").json()) == 2
        assert target.get('/api/side-conversations/' + mapping[conversation]).status_code == 200
        assert not target.get('/api/backups/settings').json()['enabled']
        assert target.get('/api/backups').json() == []
        backup(target, include_sidebar=True)


def test_restart_preserves_settings_history_and_recovers_interrupted_run(tmp_path):
    database = tmp_path / 'restart.sqlite3'
    with TestClient(create_app(database), headers=HEADERS) as client:
        configure(client, enabled=True, interval_minutes=30, keep_count=3)
        complete = run_now(client)
        service = client.app.state.backups
        interrupted, _ = storage.claim(service.database, lambda row: files.directory_for(service.database, row),
                                       BackupNow(operation_id=uuid4().hex, expected_revision=1))
    with TestClient(create_app(database), headers=HEADERS) as client:
        settings = client.get('/api/backups/settings').json()
        assert settings['enabled'] and settings['interval_minutes'] == 30 and settings['keep_count'] == 3
        history = {item['id']: item for item in client.get('/api/backups').json()}
        assert history[complete['id']]['status'] == 'ready'
        assert history[interrupted['id']]['status'] == 'interrupted'
        assert client.post(f"/api/backups/{complete['id']}/review", json={}).status_code == 200


def test_startup_scheduler_performs_due_work_without_a_browser(tmp_path):
    database = tmp_path / 'scheduler.sqlite3'
    with TestClient(create_app(database), headers=HEADERS) as client:
        configure(client, enabled=True, interval_minutes=15)
        with client.app.state.database.connect(write=True) as connection:
            connection.execute("UPDATE backup_settings SET next_run_at='2000-01-01T00:00:00+00:00'")
    with TestClient(create_app(database), headers=HEADERS) as client:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            runs = client.get('/api/backups').json()
            if runs and runs[0]['status'] != 'running':
                break
            time.sleep(0.02)
        assert len(runs) == 1 and runs[0]['status'] == 'ready'
        assert runs[0]['trigger'] == 'scheduled'
        assert client.app.state.backups.run() is None


def test_scheduled_copy_restores_exact_import_sources_and_artwork(client, tmp_path):
    original = png('v3')
    imported = stage(client, original, 'protected-character.png')
    published = publish_import(client, imported)
    assert published.status_code == 201
    character = next(item for item in published.json()['versions'] if item['kind'] == 'character')
    with_book(client, character, 'An illustrated Story')
    configure(client, enabled=True)
    run = scheduled(client)
    with TestClient(create_app(tmp_path / 'recovered-art.sqlite3'), headers=HEADERS) as target:
        archive = target.post('/api/archives/imports', json={'content': files.read_archive(run)}).json()
        _, mapping = restore(target, archive)
        assert target.get(f"/api/library-imports/{mapping[imported['id']]}/original").content == original
        image_hash = character['content']['artwork_sha256']
        assert target.get(f'/api/library-artwork/{image_hash}?size=original').content == original
        source = client.get(f"/api/versions/{character['id']}/markdown").content
        assert target.get(f"/api/versions/{mapping[character['id']]}/markdown").content == source


def test_missing_file_is_visible_and_writes_require_workspace_header(client, story):
    run = run_now(client)
    files.run_path(run).unlink()
    assert not client.get('/api/backups').json()[0]['available']
    assert client.post(f"/api/backups/{run['id']}/review", json={}).status_code == 404
    assert client.post('/api/backups', json={'operation_id': uuid4().hex, 'expected_revision': 0},
                       headers={'x-roleplay-client': ''}).status_code == 403


def test_backup_path_rejects_namespace_escape(client, story):
    run = run_now(client)
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('UPDATE backup_runs SET directory=? WHERE id=?', (str(Path(run['directory']).parent), run['id']))
    assert not client.get('/api/backups').json()[0]['available']
    assert client.post(f"/api/backups/{run['id']}/review", json={}).status_code == 409


def test_disable_during_run_keeps_frozen_copy_but_stops_next_schedule(client, story, monkeypatch):
    configure(client, enabled=True)
    original = Archives.build

    def disabling(self, body):
        configure(client, enabled=False, include_sidebar=True)
        return original(self, body)

    monkeypatch.setattr(Archives, 'build', disabling)
    run = scheduled(client)
    assert run['status'] == 'ready' and not run['settings']['include_sidebar']
    assert not json.loads(files.read_archive(run))['include_sidebar']
    assert client.app.state.backups.run(timestamp='2099-01-01T00:00:00+00:00') is None


@pytest.mark.parametrize('setting', ['workspace_id', 'revision', 'effective_directory'])
def test_clients_cannot_override_backup_identity(client, setting):
    assert client.put('/api/backups/settings', json={'expected_revision': 0, setting: 'outside'}).status_code == 422
    with client.app.state.database.connect() as connection:
        assert one(connection, 'SELECT revision FROM backup_settings')['revision'] == 0
