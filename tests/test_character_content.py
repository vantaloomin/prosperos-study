from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode, one
from server.errors import DomainError
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.side_context import branch_sources
from server.workflow.context import reference_sources
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile


def character_body():
    return {'kind': 'character', 'name': 'Iona', 'content': {
        'text': 'A patient keeper of the harbor.', 'voice': 'Direct and warm.',
        'behavior_rules': 'Ask before taking someone else’s possessions.',
        'scenario': 'The morning ferry has not arrived.', 'example_dialogue': 'Iona: Where shall we begin?',
        'author_notes': 'EDITOR ONLY: consider a later estrangement.',
        'greetings': [{'id': 'rain', 'label': 'Rain at the gate', 'text': 'Iona opens the rain-streaked gate.'},
                      {'id': 'sun', 'label': 'Sun on the quay', 'text': 'UNUSED GREETING: sunlight fills the quay.'}],
        'extension': {'preserve': [1, {'exact': 'unknown content'}]},
    }}


def opening_body(character):
    return {'operation_id': uuid4().hex, 'title': 'At the harbor',
        'opening_text': character['content']['greetings'][0]['text'],
        'opening_source': {'asset_id': character['asset_id'], 'version_id': character['id'], 'greeting_id': 'rain'},
        'attachments': [{'asset_id': character['asset_id'], 'version_id': character['id']}]}


def publish_character(client, original, content):
    response = client.post(f"/api/library/{original['asset_id']}/versions", json={
        'expected_version_id': original['id'], 'name': original['name'], 'content': content})
    assert response.status_code == 201, response.text
    return response.json()


def test_character_versions_greeting_context_and_archive_preserve_exact_sources(client):
    original = client.post('/api/library', json=character_body()).json()
    body = opening_body(original)
    profile = make_profile(client, 'Greeting reviewer')
    body['settings'] = {'primary_profile_id': profile['profile_id']}
    changed = deepcopy(original['content'])
    changed['greetings'][0]['text'] = 'The new version begins elsewhere.'
    changed['author_notes'] = 'A new editorial idea.'
    latest = publish_character(client, original, changed)
    response = client.post('/api/stories', json=body)
    assert response.status_code == 201, response.text
    story = response.json()
    assert client.post('/api/stories', json=body).json() == story
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    opening = branch['messages'][0]
    assert opening['role'] == 'assistant' and opening['text'] == body['opening_text']
    assert opening['metadata'] == {'source': 'character_greeting', **body['opening_source'], 'greeting_modified': False}
    with client.app.state.database.connect() as connection:
        snapshot, _ = generation_snapshot(connection, story['branch_id'], GenerateRequest(operation_id=uuid4().hex, expected_revision=1))
        narrative = decode(snapshot['content'])
        references = reference_sources(connection, branch['manifest_id'])
        collaborator = branch_sources(connection, one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],)))
        assert connection.execute('SELECT count(*) FROM generations').fetchone()[0] == 0
    assert 'EDITOR ONLY' not in snapshot['content'] and 'UNUSED GREETING' not in snapshot['content']
    assert snapshot['content'].count(body['opening_text']) == 1
    assert 'greetings' not in narrative['library'][0]['version']['content']
    assert 'EDITOR ONLY' not in encode(references) and 'UNUSED GREETING' not in encode(references)
    assert 'EDITOR ONLY' in encode(collaborator) and 'UNUSED GREETING' in encode(collaborator)
    assert original['content']['behavior_rules'] in encode(references)
    assert narrative['library'][0]['version']['content']['extension'] == original['content']['extension']
    history = client.get(f"/api/library/{original['asset_id']}/versions").json()
    assert [item['kind'] for item in history] == ['character', 'character']
    assert history[1]['content'] == original['content'] and history[0]['id'] == latest['id']
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/branches/{mapping[story['branch_id']]}").json()['messages'][0]
    assert restored['text'] == opening['text']
    assert restored['metadata'] == {**opening['metadata'], 'asset_id': mapping[original['asset_id']], 'version_id': mapping[original['id']]}
    broken = deepcopy(document)
    metadata = decode(broken['data']['nodes'][0]['metadata'])
    broken['data']['nodes'][0]['metadata'] = encode({**metadata, 'version_id': latest['id']})
    with pytest.raises(DomainError, match='selected'):
        parse_archive(encode(broken))


@pytest.mark.parametrize('failure', ['detached', 'disabled', 'different-version', 'missing-greeting', 'empty', 'not-character'])
def test_invalid_greeting_source_is_atomic_and_can_be_corrected(client, failure):
    original = client.post('/api/library', json=character_body()).json()
    body = opening_body(original)
    invalid = deepcopy(body)
    if failure == 'detached':
        invalid['attachments'] = []
    if failure == 'disabled':
        invalid['attachments'][0]['enabled'] = False
    if failure == 'different-version':
        latest = publish_character(client, original, original['content'])
        invalid['opening_source']['version_id'] = latest['id']
    if failure == 'missing-greeting':
        invalid['opening_source']['greeting_id'] = 'absent'
    if failure == 'empty':
        invalid['opening_text'] = '  '
    if failure == 'not-character':
        lore = client.post('/api/library', json={**character_body(), 'kind': 'lorebook'}).json()
        invalid = {**opening_body(lore), 'operation_id': body['operation_id']}
    assert client.post('/api/stories', json=invalid).status_code == 400
    assert client.get('/api/stories').json() == []
    with client.app.state.database.connect() as connection:
        assert [connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ('nodes', 'branches', 'manifests', 'operations')] == [0, 0, 0, 0]
    assert client.post('/api/stories', json=body).status_code == 201


def test_adapted_greeting_retains_original_and_survives_restore(client):
    character = client.post('/api/library', json=character_body()).json()
    body = {**opening_body(character), 'opening_text': 'Iona waits by the adapted gate.'}
    story = client.post('/api/stories', json=body).json()
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['messages'][0]['metadata']['greeting_modified'] is True
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/branches/{mapping[story['branch_id']]}").json()
    assert restored['messages'][0]['text'] == body['opening_text']
    assert restored['attachments'][0]['version']['content'] == character['content']


@pytest.mark.parametrize('content', [
    {'greetings': 'bad'}, {'greetings': [{'id': 'one', 'label': 'One', 'text': ' '}]},
    {'greetings': [{'id': 'same', 'label': 'One', 'text': 'Hi'}] * 2},
    {'behavior_rules': {'wrong': 'type'}}, {'scenario': 'x' * 100001},
])
def test_invalid_new_character_fields_leave_library_unchanged(client, content):
    response = client.post('/api/library', json={'kind': 'character', 'name': 'Invalid', 'content': content})
    assert response.status_code == 400
    assert client.get('/api/library').json() == []
