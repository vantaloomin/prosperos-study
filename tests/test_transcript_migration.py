import base64
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.format import ARCHIVE_VERSION, V51_TABLES
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.main import create_app
from server.migration.transcript_conversion import convert_transcript
from tests.test_archives import backup, restore


def st_source():
    return '\n'.join(json.dumps(item, ensure_ascii=False) for item in [
        {'user_name': 'Author', 'character_name': 'Iona', 'chat_metadata': {'private': 'SOURCE ONLY'}},
        {'name': 'System', 'is_user': False, 'is_system': True, 'mes': 'SYSTEM ONLY'},
        {'name': 'Author', 'is_user': True, 'mes': '  The gate opens.\n', 'send_date': 'source-date'},
        {'name': 'Iona', 'is_user': False, 'mes': 'The rejected reply.', 'swipe_id': 0,
         'swipes': ['The rejected reply.', 'Chosen reply ☂ <script>literal</script>'],
         'extra': {'reasoning': 'HIDDEN REASONING', 'image': 'https://example.invalid/image.png'}},
    ]).encode('utf-8')


def stage(client, raw=None, filename='chat.jsonl'):
    source = raw if raw is not None else st_source()
    response = client.post('/api/migration/transcripts', json={'filename': filename, 'source_base64': base64.b64encode(source).decode()})
    assert response.status_code == 201, response.text
    return response.json()


def body(preview, **overrides):
    return {'operation_id': uuid4().hex, 'source_sha256': preview['source_sha256'], 'title': 'A migrant Story',
            'reviewed': True, 'selections': [{'index': 1, 'variant': 0, 'role': 'user'}, {'index': 2, 'variant': 1, 'role': 'narrator'}], **overrides}


def publish(client, preview, payload=None):
    response = client.post(f"/api/migration/transcripts/{preview['id']}/publish", json=payload or body(preview))
    assert response.status_code == 201, response.text
    return response.json()


def test_st_preview_preserves_all_source_without_accepting_or_running(client):
    preview = stage(client)
    assert preview['format'] == 'sillytavern-jsonl'
    assert preview['messages'][0]['protected'] and preview['messages'][0]['proposed_role'] == 'skip'
    assert preview['messages'][2]['variants'] == ['The rejected reply.', 'Chosen reply ☂ <script>literal</script>']
    assert client.get('/api/stories').json() == []
    assert client.get(f"/api/migration/transcripts/{preview['id']}/original").content == st_source()
    assert 'HIDDEN REASONING' not in json.dumps(preview)
    result = publish(client, preview)
    branch = client.get(f"/api/branches/{result['branch_id']}").json()
    assert [node['text'] for node in branch['messages']] == ['  The gate opens.\n', 'Chosen reply ☂ <script>literal</script>']
    assert [node['role'] for node in branch['messages']] == ['user', 'narrator']
    assert branch['messages'][0]['metadata']['source_timestamp'] == 'source-date'
    assert branch['messages'][1]['metadata']['source_index'] == 2
    assert client.get(f"/api/stories/{result['story_id']}").json()['settings']['randomness']['enabled'] is False
    with client.app.state.database.connect() as connection:
        for table in ('generations', 'summary_jobs', 'summary_pending', 'relationship_jobs', 'side_threads'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


@pytest.mark.parametrize('envelope', [False, True])
def test_role_json_string_content_and_explicit_source_roles(client, envelope):
    rows = [{'role': 'system', 'content': 'Do not publish'}, {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'name': 'Mina', 'content': 'Welcome', 'alternatives': ['Goodbye']},
            {'role': 'unfamiliar', 'content': 'Needs mapping'}]
    preview = stage(client, json.dumps({'messages': rows, 'other': 'reference'} if envelope else rows).encode(), 'chat.json')
    assert [item['proposed_role'] for item in preview['messages']] == ['skip', 'user', 'assistant', 'skip']
    assert preview['messages'][2]['variants'] == ['Welcome', 'Goodbye']
    result = publish(client, preview)
    assert result['selected_messages'] == 2


@pytest.mark.parametrize('filename,text', [('chat.txt', 'Alice: First\ncontinued\nBob: Second'), ('chat.md', '## Alice\nFirst\ncontinued\n## Bob\nSecond')])
def test_text_requires_reviewed_mapping(client, filename, text):
    preview = stage(client, text.encode(), filename)
    assert [item['speaker'] for item in preview['messages']] == ['Alice', 'Bob']
    assert all(item['proposed_role'] == 'skip' for item in preview['messages'])
    payload = body(preview, selections=[{'index': 0, 'variant': 0, 'role': 'narrator'}, {'index': 1, 'variant': 0, 'role': 'ooc'}])
    result = publish(client, preview, payload)
    branch = client.get(f"/api/branches/{result['branch_id']}").json()
    assert [message['text'] for message in branch['messages']] == ['First\ncontinued', 'Second']
    export = client.post(f"/api/branches/{result['branch_id']}/transcript", json={'expected_revision': 1}).json()
    assert export['omitted_ooc_count'] == 1 and 'Second' not in export['content']


@pytest.mark.parametrize('filename,source', [
    ('bad.json', b'{"messages":[],"messages":[]}'), ('bad.json', b'[{"role":"user","content":[{"type":"image"}]}]'),
    ('bad.json', b'{"messages":[]}'), ('bad.json', b'[{"content":"No role"}]'),
    ('bad.json', b'[{"role":"user","content":"ok","alternatives":[{}]}]'), ('bad.json', b'[{"role":"user","content":NaN}]'),
    ('bad.jsonl', b'{"mes":"missing header","is_user":true}'), ('bad.jsonl', b'{"chat_metadata":{}}\n{"mes":"bad flag","is_user":1}'),
    ('bad.txt', b'\xff'), ('bad.txt', b'\0'), ('bad.txt', b''),
    ('bad.txt', ('x' * 100001).encode()), ('bad.json', json.dumps([{'role': 'user', 'content': 'ok'}] * 2001).encode()),
], ids=['duplicate-key', 'multimodal', 'empty-list', 'missing-role', 'object-alternative', 'nonfinite', 'missing-header', 'invalid-flag', 'encoding', 'nul', 'empty-text', 'long-message', 'many-messages'])
def test_unsupported_or_malformed_transcripts_are_individual_errors(client, filename, source):
    response = client.post('/api/migration/transcripts', json={'filename': filename, 'source_base64': base64.b64encode(source).decode()})
    assert response.status_code == 400, response.text
    assert client.get('/api/migration/transcripts').json() == []
    assert client.get('/api/stories').json() == []


@pytest.mark.parametrize('selection', [
    [{'index': 0, 'variant': 0, 'role': 'assistant'}],
    [{'index': 1, 'variant': 4, 'role': 'user'}],
    [{'index': 50, 'variant': 0, 'role': 'user'}],
    [{'index': 2, 'variant': 0, 'role': 'user'}, {'index': 1, 'variant': 0, 'role': 'user'}],
    [{'index': 1, 'variant': 0, 'role': 'user'}] * 2,
])
def test_invalid_mappings_cannot_accept_prose(client, selection):
    preview = stage(client)
    response = client.post(f"/api/migration/transcripts/{preview['id']}/publish", json=body(preview, selections=selection))
    assert response.status_code == 400 and client.get('/api/stories').json() == []


def test_explicit_review_source_integrity_and_retry_identity(client):
    preview = stage(client)
    endpoint = f"/api/migration/transcripts/{preview['id']}/publish"
    assert client.post(endpoint, json=body(preview, reviewed=False)).status_code == 422
    assert client.post(endpoint, json=body(preview, source_sha256='0' * 64)).status_code == 409
    payload = body(preview)
    result = publish(client, preview, payload)
    assert publish(client, preview, payload) == result
    assert client.post(endpoint, json={**payload, 'title': 'Other'}).status_code == 409
    assert len(client.get('/api/stories').json()) == 1


def test_duplicate_source_and_content_require_deliberate_new_story(client):
    first = stage(client)
    created = publish(client, first)
    same = stage(client)
    assert same['duplicates'][0]['match'] == 'exact-source'
    skipped = publish(client, same)
    assert skipped['status'] == 'skipped'
    changed_metadata = stage(client, st_source().replace(b'SOURCE ONLY', b'DIFFERENT METADATA'))
    assert changed_metadata['duplicates'][0]['match'] == 'message-content'
    assert publish(client, changed_metadata)['status'] == 'skipped'
    new = publish(client, changed_metadata, body(changed_metadata, duplicate_action='new'))
    assert new['story_id'] != created['story_id']
    different = stage(client, st_source().replace(b'The gate opens.', b'The gate closes.'))
    assert different['duplicates'] == []  # Identical filename and character names are not identity.
    assert publish(client, different)['status'] == 'imported'


def test_sources_receipts_prose_and_alternatives_survive_fresh_restore(client, tmp_path):
    preview = stage(client)
    created = publish(client, preview)
    _, document = backup(client, created)
    assert document['version'] == ARCHIVE_VERSION
    assert len(document['data']['migration_sources']) == len(document['data']['story_imports']) == 1
    with TestClient(create_app(tmp_path / 'restored.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as other:
        file = other.post('/api/archives/imports', json={'content': json.dumps(document)}).json()
        result, mapping = restore(other, file)
        new_story = result['selection']['storyId']
        origins = other.get(f'/api/stories/{new_story}/imports').json()
        assert origins[0]['import_id'] == mapping[preview['id']]
        assert other.get(f"/api/migration/transcripts/{mapping[preview['id']]}/original").content == st_source()
        branch = other.get(f"/api/branches/{result['selection']['branchId']}").json()
        assert branch['messages'][1]['metadata']['migration_receipt_id'] == mapping[created['receipt_id']]
        assert origins[0]['receipt']['selections'][1]['node_id'] == branch['messages'][1]['id']
        assert len(other.get(f"/api/migration/transcripts/{mapping[preview['id']]}").json()['messages'][2]['variants']) == 2
        backup(other)  # Re-export validates remapped receipt and source links again.
    with TestClient(create_app(tmp_path / 'restored.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as restarted:
        assert restarted.get(f'/api/stories/{new_story}/imports').json()[0]['receipt']['title'] == 'A migrant Story'
        assert restarted.get('/api/migration/transcripts').json()[0]['imported_stories'] == 1


@pytest.mark.parametrize('change', ['conversion', 'hash', 'mapping', 'prose', 'receipt-link'])
def test_archive_rejects_tampered_transcript_provenance(client, change):
    preview = stage(client)
    publish(client, preview)
    _, document = backup(client)
    if change == 'conversion':
        conversion = decode(document['data']['migration_sources'][0]['conversion'])
        conversion['messages'][1]['variants'][0] = 'forged'
        document['data']['migration_sources'][0]['conversion'] = encode(conversion)
    elif change == 'hash':
        document['data']['migration_sources'][0]['content_sha256'] = '0' * 64
    elif change == 'mapping':
        receipt = decode(document['data']['story_imports'][0]['receipt'])
        receipt['selections'][0]['index'] = 0
        document['data']['story_imports'][0]['receipt'] = encode(receipt)
    elif change == 'prose':
        document['data']['nodes'][0]['text'] = 'forged'
    else:
        document['data']['story_imports'] = []
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


def test_v51_upgrade_adds_empty_transcript_groups_and_rejects_false_provenance(client):
    client.post('/api/stories', json={'title': 'Legacy', 'opening_text': 'Existing prose'})
    _, document = backup(client)
    legacy = {**document, 'version': 51, 'data': {table: deepcopy(document['data'][table]) for table in V51_TABLES}}
    upgraded = parse_archive(json.dumps(legacy))
    assert upgraded['version'] == ARCHIVE_VERSION and upgraded['data']['migration_sources'] == []
    legacy['data']['nodes'][0]['metadata'] = encode({'source': 'transcript_import'})
    assert client.post('/api/archives/imports', json={'content': json.dumps(legacy)}).status_code == 400


def test_import_failure_rolls_back_new_story_and_receipt(client, monkeypatch):
    preview = stage(client)
    def fail(*_args, **_kwargs):
        raise RuntimeError('Injected insertion failure')
    monkeypatch.setattr('server.migration.transcripts.insert_node', fail)
    with pytest.raises(RuntimeError, match='Injected'):
        publish(client, preview)
    assert client.get('/api/stories').json() == []
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM story_imports').fetchone()[0] == 0


def test_transcript_upload_and_alternative_bounds():
    with pytest.raises(ValueError, match='10 MiB'):
        convert_transcript('chat.txt', b'x' * (10 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='100 text alternatives'):
        convert_transcript('chat.json', json.dumps([{'role': 'user', 'content': 'ok', 'alternatives': ['x'] * 101}]).encode())


@pytest.mark.parametrize('role', [' System ', 'developer', 'tool', 'function'])
def test_protected_json_roles_stay_reference_only(client, role):
    preview = stage(client, json.dumps([{'role': role, 'content': 'Source instruction'}]).encode(), 'roles.json')
    assert preview['messages'][0]['protected'] and preview['messages'][0]['source_role'] == role
    response = client.post(f"/api/migration/transcripts/{preview['id']}/publish", json=body(preview, selections=[{'index': 0, 'variant': 0, 'role': 'narrator'}]))
    assert response.status_code == 400 and client.get('/api/stories').json() == []


def test_import_preserves_existing_story_and_can_fork_without_changing_receipt(client):
    original = client.post('/api/stories', json={'title': 'Original', 'opening_text': 'Keep this path.'}).json()
    before = client.get(f"/api/branches/{original['branch_id']}").json()
    preview = stage(client)
    imported = publish(client, preview)
    branch = client.get(f"/api/branches/{imported['branch_id']}").json()
    origins = client.get(f"/api/stories/{imported['story_id']}/imports").json()
    fork = client.post(f"/api/branches/{imported['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 1, 'node_id': branch['messages'][1]['id'],
        'name': 'Later revision', 'replacement': 'A later author revision.'})
    assert fork.status_code == 201, fork.text
    assert client.get(f"/api/branches/{original['branch_id']}").json() == before
    assert client.get(f"/api/stories/{imported['story_id']}/imports").json() == origins
    file, _ = backup(client, imported)
    restored, _ = restore(client, file)
    backup(client, {'story_id': restored['selection']['storyId'], 'branch_id': restored['selection']['branchId']})
