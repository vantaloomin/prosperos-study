import json
from copy import deepcopy
from pathlib import Path

import pytest

from server.archives.validate import parse_archive
from server.database import Database, decode, encode, identifier, now
from server.errors import DomainError
from server.library_formats.files import SourceFiles
from server.library_formats.sources import source_hash
from tests.archive_legacy import remove_authoring
from tests.test_archives import backup, restore
from tests.test_library import create_book, with_book


def source(client, book):
    response = client.get(f"/api/library/{book['asset_id']}/markdown", params={'version_id': book['id']})
    assert response.status_code == 200, response.text
    return response.json()


def publish_file(client, book, text, expected_hash=None):
    return client.post(f"/api/library/{book['asset_id']}/versions", json={
        'expected_version_id': book['id'], 'expected_source_hash': expected_hash,
        'name': book['name'], 'content': {**book['content'], 'text': text}, 'note': 'Reviewed Markdown'})


def test_real_files_external_review_version_pins_and_exact_download(client, monkeypatch):
    first = create_book(client)
    story = with_book(client, first, 'Pinned world')
    original = source(client, first)
    path = Path(original['file_path'])
    assert path.read_bytes() == b'Rain every day.'
    external = '\n# The city\r\n\r\nA dry season. 🌤️\n\n'
    path.write_bytes(external.encode('utf-8'))
    changed = source(client, first)
    assert changed['changed'] and changed['sha256'] == source_hash(external)
    assert publish_file(client, first, 'Unreviewed UI change').status_code == 409
    response = publish_file(client, first, external, changed['sha256'])
    assert response.status_code == 201, response.text
    second = response.json()
    assert second['number'] == 2 and second['content']['text'] == external
    new_path = Path(source(client, second)['file_path'])
    assert new_path != path and new_path.read_bytes() == path.read_bytes() == external.encode('utf-8')
    assert client.get(f"/api/versions/{first['id']}/markdown").content == b'Rain every day.'
    assert client.get(f"/api/versions/{second['id']}/markdown").content == external.encode('utf-8')
    assert publish_file(client, first, external, changed['sha256']).status_code == 409
    # Indexed branch context must not inspect working files or object storage.
    monkeypatch.setattr('server.library_formats.files.read_markdown', lambda _path: pytest.fail('Branch retrieval scanned the filesystem'))
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['attachments'][0]['version_id'] == first['id']
    assert branch['attachments'][0]['version']['content']['text'] == 'Rain every day.'


def test_second_file_change_is_rejected_without_losing_either_draft(client):
    book = create_book(client)
    path = Path(source(client, book)['file_path'])
    path.write_text('External edit one.', encoding='utf-8')
    reviewed = source(client, book)
    path.write_text('External edit two.', encoding='utf-8')
    response = publish_file(client, book, 'Reviewed edit one + local change.', reviewed['sha256'])
    assert response.status_code == 409
    assert path.read_text(encoding='utf-8') == 'External edit two.'
    assert len(client.get(f"/api/library/{book['asset_id']}/versions").json()) == 1


@pytest.mark.parametrize('damaged_bytes', [b'Accidental snapshot edit.', b'\xff\x00binary edit'])
def test_missing_and_modified_snapshot_recovery_is_reviewed_and_retains_edits(client, damaged_bytes):
    book = create_book(client)
    before = source(client, book)
    path = Path(before['file_path'])
    path.unlink()
    missing = source(client, book)
    assert missing['missing'] and missing['markdown'] is None
    assert publish_file(client, book, 'Cannot erase a missing draft.').status_code == 409
    endpoint = f"/api/library/{book['asset_id']}/markdown/recover"
    body = {'version_id': book['id'], 'target': 'working', 'expected_hash': None}
    assert client.post(endpoint, json=body).status_code == 200
    assert path.read_text(encoding='utf-8') == book['content']['text']
    assert client.post(endpoint, json=body).status_code == 409
    files = SourceFiles(client.app.state.database)
    published = files.object_path(before['published_sha256'])
    published.write_bytes(damaged_bytes)
    damaged = source(client, book)
    assert damaged['snapshot_needs_recovery']
    assert client.get(f"/api/versions/{book['id']}/markdown").status_code == 409
    body = {'version_id': book['id'], 'target': 'published', 'expected_hash': damaged['snapshot_hash']}
    result = client.post(endpoint, json=body)
    assert result.status_code == 200, result.text
    assert Path(result.json()['retained_file']).read_bytes() == damaged_bytes
    assert not result.json()['snapshot_needs_recovery']
    assert published.read_text(encoding='utf-8') == book['content']['text']


def test_source_write_failure_rolls_back_version_head_and_leaves_original_file(client, monkeypatch):
    book = create_book(client)
    before = source(client, book)
    def fail(_path, _content):
        raise OSError('simulated full disk')
    monkeypatch.setattr('server.library_formats.files.exclusive_write', fail)
    response = publish_file(client, book, 'New unpublished text')
    assert response.status_code == 503
    assert client.get('/api/library').json()[0]['id'] == book['id']
    assert Path(before['file_path']).read_text(encoding='utf-8') == book['content']['text']
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT count(*) FROM asset_versions').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM asset_sources').fetchone()[0] == 1


def test_legacy_migration_preserves_versions_metadata_and_existing_orphan_working_file(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    database = Database(path)
    asset_id, version_id = identifier(), identifier()
    content = {'text': '# Old world\n\n', 'unknown': {'keep': True}}
    with database.connect(write=True) as connection:
        connection.execute('INSERT INTO assets VALUES (?,?,?,?)', (asset_id, 'lorebook', version_id, now()))
        connection.execute('INSERT INTO asset_versions VALUES (?,?,?,?,?,?,?)', (version_id, asset_id, 1, 'Old world', encode(content), 'Original', now()))
    working = SourceFiles(database).working_path(asset_id, version_id)
    working.parent.mkdir(parents=True)
    working.write_text('A recovered external edit.', encoding='utf-8')
    restarted = Database(path)
    assert working.read_text(encoding='utf-8') == 'A recovered external edit.'
    with restarted.connect() as connection:
        row = connection.execute('SELECT * FROM asset_versions WHERE id=?', (version_id,)).fetchone()
        assert decode(row['content']) == content and row['number'] == 1
        saved = connection.execute('SELECT * FROM asset_sources WHERE version_id=?', (version_id,)).fetchone()
        assert saved['markdown'] == content['text'] and saved['sha256'] == source_hash(content['text'])
    Database(path)  # Idempotent migration does not reset the working copy.
    assert working.read_text(encoding='utf-8') == 'A recovered external edit.'


def test_archive_restores_exact_sources_and_unpublished_whitespace_without_adopting_them(client):
    book = create_book(client)
    story = with_book(client, book, 'Archived world')
    old = source(client, book)
    text = '\n  # Unpublished file\r\nKeep the final blank line.\n\n'
    Path(old['file_path']).write_bytes(text.encode('utf-8'))
    file, document = backup(client, story)
    assert document['version'] == 19
    assert document['library_drafts'] == {book['id']: text}
    assert document['data']['asset_sources'][0]['markdown'] == book['content']['text']
    _, mapping = restore(client, file)
    restored_book = {**book, 'id': mapping[book['id']], 'asset_id': mapping[book['asset_id']]}
    restored_source = source(client, restored_book)
    assert restored_source['changed']
    assert Path(restored_source['file_path']).read_bytes() == text.encode('utf-8')
    assert client.get(f"/api/versions/{restored_book['id']}/markdown").content == book['content']['text'].encode('utf-8')
    restored_story = client.get(f"/api/stories/{mapping[story['story_id']]}").json()
    assert restored_story['attachments'][0]['version']['content'] == book['content']
    broken = deepcopy(document)
    broken['data']['asset_sources'][0]['markdown'] = 'Forged world'
    broken['data']['asset_sources'][0]['sha256'] = source_hash('Forged world')
    with pytest.raises(DomainError, match='immutable'):
        parse_archive(json.dumps(broken))
    old_archive = deepcopy(document)
    remove_authoring(old_archive)
    old_archive['version'] = 11
    old_archive['data'].pop('library_imports', None)
    old_archive['data'].pop('asset_import_origins', None)
    old_archive['data'].pop('asset_sources')
    old_archive.pop('library_drafts')
    upgraded = parse_archive(json.dumps(old_archive))
    assert upgraded['version'] == 19 and upgraded['data']['asset_sources'] == document['data']['asset_sources']


def test_archive_preserves_a_deliberately_missing_working_file(client):
    book = create_book(client)
    Path(source(client, book)['file_path']).unlink()
    file, document = backup(client)
    assert document['library_drafts'][book['id']] is None
    _, mapping = restore(client, file)
    restored = {**book, 'id': mapping[book['id']], 'asset_id': mapping[book['asset_id']]}
    assert source(client, restored)['missing']
    assert client.get(f"/api/versions/{restored['id']}/markdown").content == book['content']['text'].encode('utf-8')


def test_legacy_nontext_metadata_and_dependency_remapping_survive_file_migration(client):
    dependency = create_book(client)
    asset_id, version_id = identifier(), identifier()
    content = {'text': {'legacy': [1, False]}, 'lorebook_versions': [dependency['id']], 'unknown': {'keep': True}}
    database = client.app.state.database
    with database.connect(write=True) as connection:
        connection.execute('INSERT INTO assets VALUES (?,?,?,?)', (asset_id, 'lorebook', version_id, now()))
        connection.execute('INSERT INTO asset_versions VALUES (?,?,?,?,?,?,?)',
            (version_id, asset_id, 1, 'Legacy metadata', encode(content), 'Preserved legacy shape', now()))
    Database(database.path)
    original = source(client, {'asset_id': asset_id, 'id': version_id})
    assert original['format'] == 'legacy-metadata'
    file, _ = backup(client)
    _, mapping = restore(client, file)
    restored = source(client, {'asset_id': mapping[asset_id], 'id': mapping[version_id]})
    assert restored['format'] == 'legacy-metadata' and not restored['changed']
    history = client.get(f"/api/library/{mapping[asset_id]}/versions").json()
    assert history[0]['content'] == {**content, 'lorebook_versions': [mapping[dependency['id']]]}
