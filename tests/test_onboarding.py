from uuid import uuid4

import pytest

from server.database import decode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.scenes.context import story_context
from server.stories import Stories
from tests.test_library import create_book, publish
from tests.test_profiles import make_profile


def starting_body(client):
    writer = make_profile(client, 'Setup writer')
    book = create_book(client)
    return {'operation_id': uuid4().hex, 'title': 'The first spark', 'premise': 'Guidance, not spoken prose.',
            'opening_text': 'The lamp was already lit.',
            'settings': {'primary_profile_id': writer['profile_id'], 'experience': 'directed',
                         'genre': 'Everyday life', 'tone': 'Gentle', 'pov': 'third person', 'tense': 'past',
                         'response_length': 'Two paragraphs', 'persona': 'Direct the cast', 'player_agency': 'shared',
                         'randomness': {'enabled': True, 'chance': 10, 'cooldown': 4}},
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}


def test_setup_atomic_receipt_opening_and_no_automatic_work(client):
    body = starting_body(client)
    response = client.post('/api/stories', json=body)
    assert response.status_code == 201
    result = response.json()
    assert client.post('/api/stories', json=body).json() == result
    assert client.post('/api/stories', json={**body, 'opening_text': 'Changed.'}).status_code == 409
    branch = client.get(f"/api/branches/{result['branch_id']}").json()
    assert [(item['role'], item['text']) for item in branch['messages']] == [('narrator', body['opening_text'])]
    assert branch['revision'] == 1
    with client.app.state.database.connect() as connection:
        tables = ('stories', 'branches', 'nodes', 'manifests', 'operations')
        assert [connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables] == [1] * 5
        jobs = ('generations', 'scene_runs', 'review_runs', 'mechanic_opportunities', 'side_turns')
        assert [connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in jobs] == [0] * 5


@pytest.mark.parametrize('failure', ['profile', 'attachment'])
def test_invalid_setup_leaves_no_partial_story_and_same_operation_can_be_corrected(client, failure):
    body = starting_body(client)
    invalid = {**body, 'settings': {**body['settings'], 'primary_profile_id': 'missing'}}
    if failure == 'attachment':
        invalid = {**body, 'attachments': [{'asset_id': 'missing', 'version_id': 'missing'}]}
    assert client.post('/api/stories', json=invalid).status_code == 404
    assert client.get('/api/stories').json() == []
    with client.app.state.database.connect() as connection:
        tables = ('branches', 'manifests', 'nodes', 'operations')
        assert [connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables] == [0] * 4
    assert client.post('/api/stories', json=body).status_code == 201


def test_opening_failure_rolls_back_then_original_request_can_retry(client, monkeypatch):
    from server.models import StoryCreate

    body = StoryCreate(**starting_body(client))
    service = Stories(client.app.state.database)
    with monkeypatch.context() as patch:
        patch.setattr('server.stories.save_opening', lambda *_args: (_ for _ in ()).throw(RuntimeError('Disk failure fixture')))
        with pytest.raises(RuntimeError, match='Disk failure fixture'):
            service.create(body)
    assert service.list() == []
    result = service.create(body)
    assert service.create(body) == result


def test_selected_version_is_pinned_even_when_library_publishes_before_start(client):
    body = starting_body(client)
    book = client.get('/api/library').json()[0]
    updated = publish(client, book)
    result = client.post('/api/stories', json=body).json()
    detail = client.get(f"/api/stories/{result['story_id']}").json()
    assert detail['attachments'][0]['version_id'] == book['id']
    assert updated['id'] != book['id']
    assert detail['attachments'][0]['update_available']
    branch = client.get(f"/api/branches/{result['branch_id']}").json()
    assert branch['attachments'][0]['version_id'] == book['id']


def test_preferences_reach_future_context_without_rewriting_opening(client):
    body = starting_body(client)
    result = client.post('/api/stories', json=body).json()
    database = client.app.state.database
    request = GenerateRequest(operation_id=uuid4().hex, expected_revision=1)
    with database.connect() as connection:
        snapshot, profiles = generation_snapshot(connection, result['branch_id'], request)
        constraints = story_context(one(connection, 'SELECT * FROM stories WHERE id=?', (result['story_id'],)))
    assert decode(snapshot['content'])['story']['settings']['response_length'] == 'Two paragraphs'
    assert profiles[0]['profile_id'] == body['settings']['primary_profile_id']
    assert constraints['constraints']['experience'] == 'directed'
    detail = client.get(f"/api/stories/{result['story_id']}").json()
    changed = {**detail['settings'], 'response_length': 'One paragraph', 'experience': 'scene'}
    response = client.put(f"/api/stories/{result['story_id']}", json={
        'title': detail['title'], 'premise': detail['premise'], 'settings': changed, 'expected_revision': detail['revision']})
    assert response.status_code == 200
    with database.connect() as connection:
        future, _profiles = generation_snapshot(connection, result['branch_id'], request)
    assert decode(future['content'])['story']['settings']['response_length'] == 'One paragraph'
    assert decode(snapshot['content'])['story']['settings']['response_length'] == 'Two paragraphs'
    assert response.json()['settings']['primary_profile_id'] == body['settings']['primary_profile_id']
    assert client.get(f"/api/branches/{result['branch_id']}").json()['messages'][0]['text'] == body['opening_text']


def test_manual_setup_needs_no_profile_and_creates_an_empty_path(client):
    response = client.post('/api/stories', json={'operation_id': uuid4().hex, 'title': 'Manual',
                                              'settings': {'primary_profile_id': None}})
    assert response.status_code == 201
    branch = client.get(f"/api/branches/{response.json()['branch_id']}").json()
    assert branch['messages'] == []
    assert branch['revision'] == 0
