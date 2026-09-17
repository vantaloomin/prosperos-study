import json
import sqlite3
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.validate import parse_archive
from server.database import SCHEMA, Database, one
from server.errors import DomainError
from server.main import create_app
from server.side_context import branch_sources
from server.workflow.context import reference_sources
from tests.test_archives import backup, restore
from tests.test_authoring import AuthoringProvider, request, start
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_library import adoption_request, with_book
from tests.test_profiles import make_profile


def persona(client, name='Mara'):
    response = client.post('/api/library', json={'kind': 'persona', 'name': name, 'content': {
        'text': 'A cartographer who distrusts easy answers.\n', 'address': 'Mara', 'pronouns': 'she/her',
        'author_notes': 'Private editorial note, not a character fact.'}})
    assert response.status_code == 201, response.text
    return response.json()


def test_legacy_asset_schema_migrates_exactly_once_preserving_rows_objects_and_constraints(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    schema = SCHEMA.replace("('character','lorebook','persona')", "('character','lorebook')")
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.execute("INSERT INTO assets VALUES ('old','character','old-v1','yesterday')")
        connection.execute("INSERT INTO asset_versions VALUES ('old-v1','old',1,'Old','{}','','yesterday')")
        connection.execute('CREATE INDEX asset_kind_fixture ON assets(kind)')
        before = connection.execute('SELECT rowid,* FROM assets').fetchall()
        version = connection.execute('SELECT * FROM asset_versions').fetchall()
    Database(path)
    database = Database(path)
    with database.connect() as connection:
        assert [tuple(row) for row in connection.execute('SELECT rowid,* FROM assets')] == before
        assert [tuple(row) for row in connection.execute('SELECT * FROM asset_versions')] == version
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name='asset_kind_fixture'").fetchone()
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE asset_versions SET name='Changed' WHERE id='old-v1'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO assets VALUES ('invalid','unexpected',NULL,'now')")


def test_failed_schema_migration_rolls_back_instead_of_repairing_missing_history(tmp_path):
    path = tmp_path / 'broken-legacy.sqlite3'
    schema = SCHEMA.replace("('character','lorebook','persona')", "('character','lorebook')")
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.execute("INSERT INTO asset_versions VALUES ('orphan','missing',1,'Retain me','{}','','yesterday')")
    with pytest.raises(sqlite3.IntegrityError, match='broken references'):
        Database(path)
    with sqlite3.connect(path) as connection:
        assert "'persona'" not in connection.execute("SELECT sql FROM sqlite_master WHERE name='assets'").fetchone()[0]
        assert connection.execute('SELECT name FROM asset_versions').fetchone()[0] == 'Retain me'
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name='assets_with_personas'").fetchone() is None


@pytest.mark.parametrize('content', [{'text': 42}, {'address': 'x'*1001}, {'pronouns': 'x'*301},
                                   {'voice': 42}, {'greetings': 'invalid'}])
def test_invalid_persona_content_cannot_publish_partial_assets(client, content):
    response = client.post('/api/library', json={'kind': 'persona', 'name': 'Invalid', 'content': content})
    assert response.status_code == 400
    assert client.get('/api/library').json() == []


def test_legacy_personas_attach_as_multiple_characters(client):
    first, second = persona(client), persona(client, 'Another viewpoint')
    attachments = [{'asset_id': item['asset_id'], 'version_id': item['id']} for item in (first, second)]
    response = client.post('/api/stories', json={'title': 'Two characters', 'attachments': attachments})
    assert response.status_code == 201, response.text
    detail = client.get(f"/api/stories/{response.json()['story_id']}").json()
    assert {item['asset_id'] for item in detail['attachments']} == {first['asset_id'], second['asset_id']}
    assert all(item['enabled'] for item in detail['attachments'])


def test_persona_context_adoption_and_historical_fork_keep_identity_and_agency(client):
    identity = persona(client)
    a, b = with_book(client, identity, 'A'), with_book(client, identity, 'B')
    node = append(client, a['branch_id'], 'The map lay open.', 0)
    make_profile(client, 'Protocol fixture', primary=True)
    client.app.state.runner.provider = DraftProvider()
    run = finished(client, generate(client, a, revision=1)['id'])
    snapshot = run['snapshot']
    context = json.loads(snapshot['content'])
    selected = context['library'][0]
    assert selected['kind'] == 'character' and selected['version_id'] == identity['id']
    assert selected['version']['content']['address'] == 'Mara'
    assert selected['version']['content']['text'] == identity['content']['text']
    assert 'author_notes' not in selected['version']['content']
    assert 'player_agency' not in context['story']['settings']
    with client.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (a['branch_id'],))
        assert 'Private editorial' not in json.dumps(reference_sources(connection, branch['manifest_id']))
        assert 'Private editorial' in json.dumps(branch_sources(connection, branch))
    next_version = client.post(f"/api/library/{identity['asset_id']}/versions", json={
        'expected_version_id': identity['id'], 'name': 'Mara older', 'content': {**identity['content'], 'text': 'A retired cartographer.'}}).json()
    assert client.get(f"/api/stories/{a['story_id']}").json()['attachments'][0]['version_id'] == identity['id']
    endpoint = f"/api/versions/{next_version['id']}/adoption"
    assert client.post(endpoint, json=adoption_request(client.get(endpoint).json())).json() == {'updated': 2}
    assert client.get(f"/api/stories/{b['story_id']}").json()['attachments'][0]['version_id'] == next_version['id']
    assert client.get(f"/api/generations/{run['id']}").json()['snapshot'] == snapshot
    fork = client.post(f"/api/branches/{a['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 2, 'node_id': node,
        'name': 'Earlier identity', 'replacement': 'The old map lay open.'}).json()
    assert client.get(f"/api/branches/{fork['branch_id']}").json()['attachments'][0]['version_id'] == identity['id']


def test_persona_archive_restores_shared_identity_and_rejects_invalid_old_format(client, tmp_path):
    identity = persona(client)
    a, b = with_book(client, identity, 'A'), with_book(client, identity, 'B')
    _, document = backup(client)
    assert document['version'] == 19
    with TestClient(create_app(tmp_path/'restored.sqlite3'), headers={'x-roleplay-client':'workspace'}) as target:
        uploaded = target.post('/api/archives/imports', json={'content': json.dumps(document)})
        assert uploaded.status_code == 201, uploaded.text
        _, mapping = restore(target, uploaded.json())
        left = target.get(f"/api/stories/{mapping[a['story_id']]}").json()
        right = target.get(f"/api/stories/{mapping[b['story_id']]}").json()
        assert left['attachments'][0]['asset_id'] == right['attachments'][0]['asset_id'] == mapping[identity['asset_id']]
        restored = target.get(f"/api/library/{mapping[identity['asset_id']]}/versions").json()[0]
        assert restored['content'] == identity['content'] and restored['kind'] == 'persona'
    old = deepcopy(document)
    old['version'] = 16
    with pytest.raises(DomainError, match='Version 16'):
        parse_archive(json.dumps(old))
    broken = deepcopy(document)
    broken['data']['asset_versions'][0]['content'] = json.dumps({'greetings': 'invalid'})
    with pytest.raises(DomainError):
        parse_archive(json.dumps(broken))


def test_persona_authoring_is_reviewable_and_never_publishes_or_changes_story(client):
    identity = persona(client)
    story = with_book(client, identity, 'Unchanged Story')
    make_profile(client, 'Protocol fixture', primary=True)
    provider = AuthoringProvider()
    client.app.state.authoring_runner.provider = provider
    before = client.get(f"/api/stories/{story['story_id']}").json()
    run = start(client, request(identity, kind='persona', target_label='Persona & background', text=identity['content']['text']))
    assert run['jobs'][0]['status'] == 'done'
    assert 'character, persona or lorebook' in provider.calls[0][1]
    assert client.get(f"/api/stories/{story['story_id']}").json() == before
    assert client.get(f"/api/library/{identity['asset_id']}/versions").json() == [identity]


def test_legacy_character_accepts_character_authoring_and_archives(client):
    from server.archives.validate import parse_archive
    identity = persona(client)
    make_profile(client, 'Primary', primary=True)
    client.app.state.authoring_runner.provider = AuthoringProvider()
    run = start(client, request(identity, kind='character', target_label='Character & background', text=identity['content']['text']))
    assert run['jobs'][0]['status'] == 'done'
    _, document = backup(client)
    assert parse_archive(json.dumps(document))['version'] == 19


def test_character_card_can_publish_over_legacy_persona_without_changing_identity(client):
    from tests.test_library_imports import card, stage
    identity = persona(client)
    preview = stage(client, json.dumps(card()).encode())
    choice = next(item for item in preview['drafts'] if item['part'] == 'character')
    body = {'operation_id': uuid4().hex, 'source_sha256': preview['source_sha256'], 'reviewed_compatibility': True,
            'choices': [{'part': 'character', 'name': choice['name'], 'content': choice['content'],
                         'target_asset_id': identity['asset_id'], 'expected_version_id': identity['id']}]}
    response = client.post(f"/api/library-imports/{preview['id']}/publish", json=body)
    assert response.status_code == 201, response.text
    version = response.json()['versions'][0]
    assert version['asset_id'] == identity['asset_id'] and version['number'] == 2
    assert client.get(f"/api/library/{identity['asset_id']}/versions").json()[-1] == identity
    _, document = backup(client)
    assert parse_archive(json.dumps(document))['version'] == 19
