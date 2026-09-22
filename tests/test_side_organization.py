import json
from copy import deepcopy
from uuid import uuid4

from server.archives.format import V40_TABLES
from server.database import Database
from server.side_conversations import SideConversations
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile
from tests.test_sidebar import CollaboratorProvider, ask, settle, story_state, thread


def organize(client, identity, name='A useful discussion', archived=False):
    current = client.get(f'/api/side-conversations/{identity}').json()
    body = {'operation_id': uuid4().hex, 'expected_revision': current['curation']['revision'],
            'name': name, 'archived': archived}
    endpoint = f'/api/side-conversations/{identity}/organization'
    response = client.put(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert client.put(endpoint, json=body).json() == response.json()
    return response.json()


def search(client, story, query='', **options):
    response = client.get(f"/api/stories/{story['story_id']}/side-conversations/search", params={'query': query, **options})
    assert response.status_code == 200, response.text
    return response.json()


def discussion(client, story):
    make_profile(client, 'Companion', primary=True)
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    identity = thread(client, story)
    result = ask(client, identity, story, question='Should the [promise] cost 10%?')
    settle(client)
    return identity, result, provider


def test_rename_archive_reopen_is_idempotent_and_does_not_touch_story(client, story):
    identity, _, provider = discussion(client, story)
    before = story_state(client)
    prior = client.get(f'/api/side-conversations/{identity}').json()
    result = organize(client, identity, 'The letter and the promise', True)
    assert result['curation'] == {'archived': True, 'revision': 1}
    assert client.get(f"/api/stories/{story['story_id']}/side-conversations").json() == []
    assert client.get(f"/api/stories/{story['story_id']}/side-conversations?include_archived=true").json()[0]['id'] == identity
    after = client.get(f'/api/side-conversations/{identity}').json()
    assert after['turns'] == prior['turns']
    assert story_state(client) == before and len(provider.calls) == 1
    reopened = SideConversations(Database(client.app.state.database.path)).detail(identity)
    assert reopened == after
    organize(client, identity, archived=False)
    assert len(client.get(f"/api/stories/{story['story_id']}/side-conversations").json()) == 1


def test_stale_organization_and_non_text_fields_are_rejected(client, story):
    identity = thread(client, story)
    organize(client, identity)
    body = {'operation_id': uuid4().hex, 'expected_revision': 0, 'name': 'Stale title', 'archived': True}
    endpoint = f'/api/side-conversations/{identity}/organization'
    assert client.put(endpoint, json=body).status_code == 409
    assert client.put(endpoint, json={**body, 'expected_revision': 1, 'name': ' '}).status_code == 422
    assert client.put(endpoint, json={**body, 'expected_revision': 1, 'story_id': 'another-story'}).status_code == 422
    assert client.get(f'/api/side-conversations/{identity}').json()['name'] == 'A useful discussion'


def test_literal_search_returns_exact_question_or_reply_identity_in_same_story(client, story):
    identity, run, _ = discussion(client, story)
    question = search(client, story, '[promise]')['results'][0]
    assert question['match']['kind'] == 'question' and question['match']['match'] == '[promise]'
    assert question['match']['turn_id'] == run['id'] and question['match']['reply_id'] is None
    assert search(client, story, '10%')['total'] == 1
    answer = search(client, story, 'unopened letter')['results'][0]
    assert answer['match']['kind'] == 'reply' and answer['match']['reply_id'] == run['reply_ids'][0]
    other = client.post('/api/stories', json={'title': 'An unrelated story'}).json()
    assert search(client, other, 'unopened letter')['total'] == 0
    organize(client, identity, 'Private notes', True)
    assert search(client, story, 'unopened letter')['total'] == 0
    assert search(client, story, 'unopened letter', include_archived=True)['results'][0]['curation']['archived']
    assert search(client, story, 'private', include_archived=True)['results'][0]['match']['kind'] == 'name'


def test_search_is_paged_and_read_only(client, story):
    for _ in range(3):
        thread(client, story)
    with client.app.state.database.connect() as connection:
        before = '\n'.join(connection.iterdump())
    first = search(client, story, limit=2)
    second = search(client, story, offset=first['next_offset'], limit=2)
    assert first['total'] == 3 and len(first['results']) == 2 and len(second['results']) == 1
    assert second['next_offset'] is None
    assert not {item['id'] for item in first['results']} & {item['id'] for item in second['results']}
    with client.app.state.database.connect() as connection:
        assert '\n'.join(connection.iterdump()) == before


def test_restore_preserves_organization_and_exact_reply_receipts_when_sidebar_included(client, story):
    identity, run, provider = discussion(client, story)
    organize(client, identity, 'The archived discussion', True)
    receipt = client.get(f"/api/side-replies/{run['reply_ids'][0]}/requests/0").json()
    file, document = backup(client, story, include_sidebar=True)
    assert len(document['data']['side_thread_curation']) == 1
    _, mapping = restore(client, file)
    restored = client.get(f'/api/side-conversations/{mapping[identity]}').json()
    assert restored['name'] == 'The archived discussion' and restored['curation']['archived']
    assert client.get(f"/api/side-replies/{mapping[run['reply_ids'][0]]}/requests/0").json() == receipt
    _, private = backup(client, story, include_sidebar=False)
    assert all(private['data'][key] == [] for key in ('side_threads', 'side_thread_curation', 'side_turns', 'side_replies'))
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}, include_sidebar=True)
    _, again = restore(client, second)
    assert client.get(f'/api/side-conversations/{again[mapping[identity]]}').json()['curation'] == restored['curation']
    assert len(provider.calls) == 1


def test_v40_upgrade_requires_its_exact_groups_and_defaults_conversations_to_active(client, story):
    identity = thread(client, story)
    _, document = backup(client, story, include_sidebar=True)
    old = deepcopy(document)
    old['version'] = 40
    old['data'] = {key: old['data'][key] for key in V40_TABLES}
    imported = client.post('/api/archives/imports', json={'content': json.dumps(old)})
    assert imported.status_code == 201, imported.text
    _, mapping = restore(client, imported.json())
    assert client.get(f'/api/side-conversations/{mapping[identity]}').json()['curation'] == {'archived': False, 'revision': 0}
    old['data']['side_thread_curation'] = []
    assert client.post('/api/archives/imports', json={'content': json.dumps(old)}).status_code == 400
