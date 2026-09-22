import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import V45_TABLES
from server.database import encode
from server.operations import fingerprint
from server.side_conversations import SideQuestion
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_profiles import make_profile
from tests.test_sidebar import CollaboratorProvider, settle, story_state, thread


def read(client, identity):
    response = client.get(f'/api/side-conversations/{identity}/draft')
    assert response.status_code == 200, response.text
    return response.json()


def save(client, identity, text, version=None):
    current = read(client, identity)
    response = client.put(f'/api/side-conversations/{identity}/draft', json={'expected_version': version or current['version'], 'text': text})
    assert response.status_code == 200, response.text
    return response.json()


def body(story, draft):
    return {'operation_id': uuid4().hex, 'branch_id': story['branch_id'], 'expected_revision': 0,
            'question': draft['text'], 'expected_draft_version': draft['version']}


def setup(client, story):
    make_profile(client, 'Companion', primary=True)
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    return thread(client, story), provider


def test_shared_draft_checks_exact_version_and_preserves_whitespace_without_model_calls(client, story):
    identity, provider = setup(client, story)
    before = story_state(client)
    empty = read(client, identity)
    saved = save(client, identity, '  A question 🦉.\n')
    assert saved['text'] == '  A question 🦉.\n' and saved['basis']['revision'] == 1
    assert save(client, identity, saved['text']) == saved
    response = client.put(f'/api/side-conversations/{identity}/draft', json={'expected_version': empty['version'], 'text': 'Other view.'})
    assert response.status_code == 409 and read(client, identity) == saved
    assert provider.calls == [] and story_state(client) == before


def test_question_consumes_exact_draft_atomically_and_two_views_cannot_send_it_twice(client, story):
    identity, provider = setup(client, story)
    saved = save(client, identity, '  Why this wording? 🦉\n')
    request = body(story, saved)
    response = client.post(f'/api/side-conversations/{identity}/questions', json=request)
    assert response.status_code == 201, response.text
    settle(client)
    assert provider.calls[0]['question'] == saved['text']
    detail = client.get(f'/api/side-conversations/{identity}').json()
    assert detail['turns'][0]['question'] == saved['text']
    assert read(client, identity)['text'] == ''
    assert client.post(f'/api/side-conversations/{identity}/questions', json={**request, 'operation_id': uuid4().hex}).status_code == 409
    newer = save(client, identity, 'Later unsent question.')
    assert client.post(f'/api/side-conversations/{identity}/questions', json=request).json() == response.json()
    assert client.get(f"/api/operations/{request['operation_id']}").json()['result'] == response.json()
    assert read(client, identity) == newer and len(provider.calls) == 1


@pytest.mark.parametrize('damage', ['text', 'story', 'revision', 'profile'])
def test_rejected_question_retains_unsent_draft(client, story, damage):
    identity, provider = setup(client, story)
    saved = save(client, identity, 'Keep this question.')
    request = body(story, saved)
    if damage == 'text':
        request['question'] = 'Different words.'
    elif damage == 'story':
        other = client.post('/api/stories', json={'title': 'Other Story'}).json()
        request['branch_id'] = other['branch_id']
    elif damage == 'revision':
        append(client, story['branch_id'], 'New accepted passage.', 0)
    else:
        request['profile_ids'] = ['missing-profile']
    response = client.post(f'/api/side-conversations/{identity}/questions', json=request)
    assert response.status_code in {400, 404, 409}, response.text
    assert read(client, identity) == saved and provider.calls == []


def test_drafts_are_per_conversation_and_private_archive_disclosure_is_preserved(client, story):
    identity, _ = setup(client, story)
    other = thread(client, story)
    first, second = save(client, identity, 'First private draft.'), save(client, other, 'Second private draft.')
    _, hidden = backup(client, story)
    assert hidden['data']['side_drafts'] == [] and hidden['data']['side_threads'] == []
    file, included = backup(client, story, include_sidebar=True)
    assert len(included['data']['side_drafts']) == 2
    _, mapping = restore(client, file)
    assert read(client, mapping[identity])['text'] == first['text']
    assert read(client, mapping[other])['text'] == second['text']
    assert read(client, mapping[identity])['version'] != first['version']
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    file, _ = backup(client, copied, include_sidebar=True)
    restore(client, file)
    wrong = deepcopy(included)
    wrong['data']['side_drafts'][0]['thread_id'] = 'missing'
    assert client.post('/api/archives/imports', json={'content': json.dumps(wrong)}).status_code == 400


def test_old_question_fingerprint_and_replay_stay_compatible(client, story):
    identity, provider = setup(client, story)
    request = {'operation_id': uuid4().hex, 'branch_id': story['branch_id'], 'expected_revision': 0, 'question': 'Old request.'}
    model = SideQuestion(**request).model_dump()
    assert 'expected_draft_version' not in model
    response = client.post(f'/api/side-conversations/{identity}/questions', json=request)
    assert response.status_code == 201
    settle(client)
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('UPDATE operations SET fingerprint=? WHERE id=?', (fingerprint('side-question', {'thread_id': identity, **model}), request['operation_id']))
    saved = save(client, identity, 'New unsent text.')
    assert client.post(f'/api/side-conversations/{identity}/questions', json=request).json() == response.json()
    assert read(client, identity) == saved and len(provider.calls) == 1


def test_strict_format45_upgrade_has_no_invented_conversation_drafts(client, story):
    setup(client, story)
    _, document = backup(client, story, include_sidebar=True)
    document['version'] = 45
    document['data'] = {key: document['data'][key] for key in V45_TABLES}
    assert client.post('/api/archives/imports', json={'content': encode(document)}).status_code == 201
    document['data']['side_drafts'] = []
    assert client.post('/api/archives/imports', json={'content': encode(document)}).status_code == 400
