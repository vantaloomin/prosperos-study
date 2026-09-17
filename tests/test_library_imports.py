import base64
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest

from server.archives.validate import parse_archive
from server.character_content import narrative_asset
from server.database import one
from server.errors import DomainError
from server.side_context import branch_sources
from tests.archive_legacy import remove_authoring
from tests.test_archives import backup, restore
from tests.test_card_markdown import card
from tests.test_library import create_book, with_book


def stage(client, source, filename='character.json'):
    response = client.post('/api/library-imports', json={'filename': filename, 'source_base64': base64.b64encode(source).decode()})
    assert response.status_code == 201, response.text
    return response.json()


def publish_body(preview):
    return {'operation_id': uuid4().hex, 'source_sha256': preview['source_sha256'], 'reviewed_compatibility': True,
            'choices': [{key: draft[key] for key in ('part', 'name', 'content')} for draft in preview['drafts']]}


def publish_import(client, preview, body=None):
    return client.post(f"/api/library-imports/{preview['id']}/publish", json=body or publish_body(preview))


@pytest.mark.parametrize('version', ['v1', 'v2', 'v3'])
def test_card_preview_publish_original_files_and_runtime_boundary(client, version):
    source = b'\xef\xbb\xbf' + json.dumps(card(version), ensure_ascii=False, indent=3).encode('utf-8')
    preview = stage(client, source)
    assert client.get('/api/library').json() == [] and client.get('/api/stories').json() == []
    assert client.get(f"/api/library-imports/{preview['id']}/original").content == source
    package = client.get(f"/api/library-imports/{preview['id']}/package")
    with ZipFile(BytesIO(package.content)) as zipped:
        assert zipped.read('source.json') == source
        assert 'converted/character.md' in zipped.namelist()
        assert all(not name.startswith('/') and '..' not in Path(name).parts for name in zipped.namelist())
    assert client.get(f"/api/library-imports/{preview['id']}/document", params={'path': '../../schema.sql'}).status_code == 404
    body = publish_body(preview)
    result = publish_import(client, preview, body)
    assert result.status_code == 201, result.text
    assert publish_import(client, preview, body).json() == result.json()
    versions = result.json()['versions']
    assert len(versions) == (1 if version == 'v1' else 2)
    character = next(item for item in versions if item['kind'] == 'character')
    content = character['content']
    data = card(version) if version == 'v1' else card(version)['data']
    assert content['text'] == data['description'] and content['voice'] == data['personality']
    narrative = narrative_asset({'kind': 'character', 'version': character})['version']['content']
    assert 'author_notes' not in narrative and 'greetings' not in narrative
    assert 'system_prompt' not in narrative and 'source_base64' not in narrative
    if version != 'v1':
        book = versions[0]
        assert book['content'] == {'text': data['character_book']['description']}
        assert content['lorebook_versions'] == [book['id']]
        assert len(content['greetings']) == 2
        assert any('inactive' in item['message'] for item in preview['issues'])
    assert client.get(f"/api/versions/{character['id']}/imports").json()[0]['id'] == preview['id']
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT count(*) FROM generations').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM mechanic_opportunities').fetchone()[0] == 0
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()


def test_plain_markdown_edit_and_existing_version_keep_story_pin_and_provenance(client):
    book = create_book(client)
    story = with_book(client, book, 'Pinned')
    original = b'\n# A new season\r\n\r\nFlowers return.\n\n'
    preview = stage(client, original, 'Seasons.md')
    assert preview['drafts'][0]['content']['text'].encode() == original
    body = publish_body(preview)
    body['choices'][0].update(target_asset_id=book['asset_id'], expected_version_id=book['id'])
    body['choices'][0]['content']['text'] += 'An author adjustment.\n'
    result = publish_import(client, preview, body)
    assert result.status_code == 201, result.text
    second = result.json()['versions'][0]
    assert second['asset_id'] == book['asset_id'] and second['number'] == 2
    assert client.get(f"/api/stories/{story['story_id']}").json()['attachments'][0]['version_id'] == book['id']
    assert client.get(f"/api/library-imports/{preview['id']}/original").content == original
    third = client.post(f"/api/library/{book['asset_id']}/versions", json={
        'expected_version_id': second['id'], 'name': second['name'], 'content': {'text': 'A later edit.'}}).json()
    assert client.get(f"/api/versions/{third['id']}/imports").json()[0]['id'] == preview['id']
    assert publish_import(client, preview).status_code == 201  # A deliberate separate import can create a separate item.


def test_conflicts_compatibility_and_atomic_multi_item_rollback(client):
    book = create_book(client)
    source = json.dumps(card()).encode()
    preview = stage(client, source)
    body = publish_body(preview)
    body['reviewed_compatibility'] = False
    assert publish_import(client, preview, body).status_code == 400
    body['reviewed_compatibility'] = True
    body['choices'][0].update(target_asset_id=book['asset_id'], expected_version_id=book['id'])
    assert publish_import(client, preview, body).status_code == 400
    assert len(client.get('/api/library').json()) == 1  # The book written first was rolled back too.
    plain = stage(client, b'Updated prose.', 'book.md')
    body = publish_body(plain)
    body['choices'][0].update(target_asset_id=book['asset_id'], expected_version_id=book['id'])
    path = Path(client.get(f"/api/library/{book['asset_id']}/markdown").json()['file_path'])
    path.write_text('External draft.', encoding='utf-8')
    assert publish_import(client, plain, body).status_code == 409
    assert path.read_text(encoding='utf-8') == 'External draft.'
    reviewed = client.get(f"/api/library/{book['asset_id']}/markdown").json()
    body['choices'][0]['expected_source_hash'] = reviewed['sha256']
    assert publish_import(client, plain, body).status_code == 201
    body['operation_id'] = uuid4().hex
    assert publish_import(client, plain, body).status_code == 409


def test_import_sources_archive_restore_and_tamper_rejection(client):
    raw = json.dumps(card(), ensure_ascii=False, indent=2).encode('utf-8')
    preview = stage(client, raw)
    versions = publish_import(client, preview).json()['versions']
    stage(client, b'An unpublished draft.', 'draft.md')
    archive, document = backup(client)
    assert document['version'] == 19 and len(document['data']['library_imports']) == 1
    _, mapping = restore(client, archive)
    assert client.get(f"/api/library-imports/{mapping[preview['id']]}/original").content == raw
    for version in versions:
        provenance = client.get(f"/api/versions/{mapping[version['id']]}/imports").json()
        assert provenance[0]['id'] == mapping[preview['id']]
    second, repeated = backup(client)
    assert len(repeated['data']['library_imports']) == 2 and second['id'] != archive['id']
    broken = deepcopy(document)
    converted = json.loads(broken['data']['library_imports'][0]['conversion'])
    converted['files']['../../escape.md'] = 'Do not write this.'
    broken['data']['library_imports'][0]['conversion'] = json.dumps(converted)
    with pytest.raises(DomainError, match='preserved original'):
        parse_archive(json.dumps(broken))
    legacy = deepcopy(document)
    remove_authoring(legacy)
    legacy['version'] = 12
    for key in ('library_imports', 'asset_import_origins'):
        legacy['data'].pop(key)
    assert parse_archive(json.dumps(legacy))['version'] == 19


def test_collaborator_can_retrieve_original_and_inactive_entries_without_progression(client):
    raw = json.dumps(card(), ensure_ascii=False).encode('utf-8')
    preview = stage(client, raw)
    character = publish_import(client, preview).json()['versions'][-1]
    story = with_book(client, character, 'Source review')
    with client.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        docs = branch_sources(connection, branch)
        original = next(doc for doc in docs if doc['id'].startswith(f"import:{preview['id']}:original:"))
        assert original['text'] == raw.decode('utf-8')
        assert 'not active instructions or accepted canon' in original['title']
        assert any('@@dont_activate' in doc['text'] for doc in docs)
        assert branch == one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        assert connection.execute('SELECT count(*) FROM nodes').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM mechanic_opportunities').fetchone()[0] == 0


def test_importing_both_parts_replaces_old_link_to_the_same_book(client):
    book = create_book(client)
    preview = stage(client, json.dumps(card()).encode())
    body = publish_body(preview)
    body['choices'][0]['content']['lorebook_versions'] = [book['id']]
    body['choices'][1].update(target_asset_id=book['asset_id'], expected_version_id=book['id'])
    result = publish_import(client, preview, body)
    assert result.status_code == 201, result.text
    second, character = result.json()['versions']
    assert second['asset_id'] == book['asset_id'] and second['number'] == 2
    assert character['content']['lorebook_versions'] == [second['id']]
    story = with_book(client, character, 'Both parts')
    attachments = client.get(f"/api/stories/{story['story_id']}").json()['attachments']
    assert {item['version_id'] for item in attachments} == {character['id'], second['id']}


@pytest.mark.parametrize('filename,source', [('card.json', b'{bad'), ('card.json', b'{"name":"a","name":"b"}'),
                                          ('book.md', b'\xffbad'), ('script.exe', b'text')])
def test_invalid_import_leaves_no_library_items(client, filename, source):
    response = client.post('/api/library-imports', json={'filename': filename, 'source_base64': base64.b64encode(source).decode()})
    assert response.status_code == 400
    assert client.get('/api/library').json() == []
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT count(*) FROM library_imports').fetchone()[0] == 0
