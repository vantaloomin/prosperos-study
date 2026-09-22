import json
from uuid import uuid4

import pytest

from tests.test_side_drafts import read, save
from tests.test_side_edits import reply, setup
from tests.test_sidebar import settle
from tests.test_writing_resources import create


def request(story, selected, draft):
    return {'operation_id': uuid4().hex, 'branch_id': story['branch_id'], 'expected_revision': 0,
            'question': draft['text'], 'expected_draft_version': draft['version'], 'context_id': selected['context']['id'],
            'expected_context_revision': selected['revision'], 'max_reads': 2, 'work': {'task': 'rewrite'}}


@pytest.mark.parametrize('mode', ['full', 'long'])
@pytest.mark.parametrize('focused', [False, True])
def test_preview_is_read_only_and_matches_exact_sent_inputs(client, mode, focused):
    story = client.post('/api/stories', json={'title': 'Preview workshop', 'settings': {'memory': {'mode': mode}}}).json()
    identity, _, selected = setup(client, story)
    draft = save(client, identity, '  Keep the exact question 🦉.\n')
    body = request(story, selected, draft)
    if not focused:
        body.pop('work')
        client.app.state.side_runner.provider.output = 'A discussion.'
    path = f'/api/side-conversations/{identity}'
    first = client.post(path + '/preview', json=body)
    assert first.status_code == 200, first.text
    preview = first.json()
    assert read(client, identity) == draft
    assert client.get(path).json()['turns'] == [] and client.app.state.side_runner.provider.calls == []
    assert preview['cost'] is None and preview['max_calls'] == 3
    assert preview['models'][0]['input_allowance'] >= preview['input_estimate']
    assert json.loads(preview['content'])['question'] == draft['text']
    second = client.post(path + '/preview', json={**body, 'operation_id': uuid4().hex})
    assert second.json() == preview
    sent = client.post(path + '/questions', json={**body, 'operation_id': uuid4().hex, 'expected_preview': preview['fingerprint']})
    assert sent.status_code == 201, sent.text
    settle(client)
    assert reply(client, identity)['status'] == 'done'
    call = client.app.state.side_runner.provider.calls[0]
    assert call[1] == preview['prompt'] and call[2] == json.loads(preview['content'])
    assert read(client, identity)['text'] == ''


@pytest.mark.parametrize('change', ['question', 'authority', 'reads', 'model'])
def test_changed_preview_cannot_consume_draft_or_call_provider(client, story, change):
    from tests.test_profiles import make_profile
    identity, _, selected = setup(client, story)
    draft = save(client, identity, 'Review this wording.')
    body = request(story, selected, draft)
    path = f'/api/side-conversations/{identity}'
    preview = client.post(path + '/preview', json=body).json()
    if change == 'question':
        draft = save(client, identity, 'A different request.')
        body.update(question=draft['text'], expected_draft_version=draft['version'])
    elif change == 'authority':
        body['work']['authority'] = 'apply'
    elif change == 'reads':
        body['max_reads'] = 1
    else:
        model = make_profile(client, 'A different Companion', primary=True)
        body['profile_ids'] = [model['profile_id']]
    response = client.post(path + '/questions', json={**body, 'expected_preview': preview['fingerprint']})
    assert response.status_code == 409 and 'preview' in response.json()['detail'], response.text
    assert read(client, identity) == draft and client.app.state.side_runner.provider.calls == []
    assert client.get(path).json()['turns'] == []
    current = client.post(path + '/preview', json=body).json()
    assert current['fingerprint'] != preview['fingerprint']
    assert client.post(path + '/questions', json={**body, 'expected_preview': current['fingerprint']}).status_code == 201
    settle(client)


def test_preview_includes_resolved_style_recipe_samples_and_fixed_selection(client, story):
    style = create(client, content={'prose': 'Spare, concrete sentences.', 'examples': [{'label': 'Example only', 'text': 'The kettle cooled.'}]})
    recipe = create(client, 'recipe', {'purpose': 'revise', 'instructions': 'Keep {{detail}}.', 'style': style['id'],
                                      'variables': [{'name': 'detail', 'label': 'Detail', 'type': 'text'}],
                                      'steps': [{'task': 'revision', 'instructions': 'Preserve dialogue.'}]}, 'Dialogue pass')
    identity, _, selected = setup(client, story)
    draft = save(client, identity, 'Restyle the selection.')
    body = request(story, selected, draft)
    body['work'] = {'task': 'apply-style', 'writing': {'recipe': recipe['id'], 'variables': {'detail': 'the letter'}}}
    response = client.post(f'/api/side-conversations/{identity}/preview', json=body)
    assert response.status_code == 200, response.text
    preview, content = response.json(), json.loads(response.json()['content'])
    assert preview['writing']['style'] == {'name': style['name'], 'number': style['number']}
    assert content['writing_guidance']['resolved_recipe']['instructions'] == 'Keep the letter.'
    assert content['writing_guidance']['style']['content']['examples'][0]['text'] == 'The kettle cooled.'
    assert content['companion_task']['selection']['text'] == 'Original'
    assert client.app.state.side_runner.provider.calls == []
