import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import V46_TABLES
from server.database import decode
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_profiles import make_profile
from tests.test_sidebar import CollaboratorProvider, settle, thread


def setup(client, story):
    make_profile(client, 'Companion context fixture', primary=True)
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    return thread(client, story), provider


def head(client, identity):
    response = client.get(f'/api/side-conversations/{identity}/context')
    assert response.status_code == 200, response.text
    return response.json()


def pin(client, identity, source, expected=None):
    request = {'operation_id': uuid4().hex, 'expected_revision': head(client, identity)['revision'] if expected is None else expected, 'source': source}
    response = client.post(f'/api/side-conversations/{identity}/context', json=request)
    assert response.status_code == 201, response.text
    assert client.post(f'/api/side-conversations/{identity}/context', json=request).json() == response.json()
    return response.json()


def branch_source(story, revision=0):
    return {'kind': 'branch', 'branch_id': story['branch_id'], 'expected_revision': revision}


def question(client, identity, selected, text='Discuss the selected source.'):
    value = selected['context']
    body = {'operation_id': uuid4().hex, 'branch_id': value['branch']['id'], 'expected_revision': value['branch']['revision'],
            'context_id': value['id'], 'expected_context_revision': selected['revision'], 'question': text}
    response = client.post(f'/api/side-conversations/{identity}/questions', json=body)
    assert response.status_code == 201, response.text
    settle(client)
    return response.json()


def text_source(client, story, node, revision=1, start=0, end=5, text='First'):
    ref = {'kind': 'passage', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'node_id': node}
    target = client.post('/api/text-targets/read', json={'target': ref}).json()
    return {'kind': 'text', 'branch_id': story['branch_id'], 'expected_revision': revision, 'target': ref,
            'expected_version': target['version'], 'selection': {'start': start, 'end': end, 'text': text}}


@pytest.mark.parametrize('mode', ['full', 'long'])
def test_pinned_selection_is_mandatory_exact_context_and_never_acquires_later_sources(client, mode):
    story = client.post('/api/stories', json={'title': 'Pinned source', 'settings': {'memory': {'mode': mode}}}).json()
    identity, provider = setup(client, story)
    node = append(client, story['branch_id'], 'First 🦉 paragraph.\n\nLater part.', 0)
    selected = pin(client, identity, text_source(client, story, node, start=6, end=8, text='🦉'))
    assert provider.calls == []
    append(client, story['branch_id'], 'FUTURE_ONLY_NEVER_IN_PIN', 1)
    question(client, identity, selected)
    context = provider.calls[0]['selected_context']
    assert context['selection'] == {'start': 6, 'end': 8, 'text': '🦉'}
    assert context['branch_revision'] == 1 and 'FUTURE_ONLY_NEVER_IN_PIN' not in json.dumps(provider.calls)
    assert client.get(f"/api/branches/{story['branch_id']}").json()['revision'] == 2
    # Repeated earlier-reply pins retain the selected range even when Long Story
    # already saved discussion documents in the previous request's archive.
    for _ in range(2):
        turn_id = client.get(f'/api/side-conversations/{identity}').json()['turns'][-1]['id']
        selected = pin(client, identity, {'kind': 'turn', 'turn_id': turn_id})
        question(client, identity, selected)
        assert provider.calls[-1]['selected_context']['selection'] == context['selection']
        assert 'FUTURE_ONLY_NEVER_IN_PIN' not in json.dumps(provider.calls[-1])
    file, _ = backup(client, story, include_sidebar=True)
    _, mapping = restore(client, file)
    restored = head(client, mapping[identity])
    assert restored['context']['target']['selection'] == context['selection']
    assert restored['context']['target']['snapshot']['ref']['node_id'] == mapping[node]
    again, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}, include_sidebar=True)
    restore(client, again)


def test_pin_head_races_and_changed_selection_leave_question_and_story_untouched(client, story):
    from tests.test_side_drafts import read, save
    identity, provider = setup(client, story)
    draft = save(client, identity, 'Keep unsent.')
    first = pin(client, identity, branch_source(story))
    second = pin(client, identity, branch_source(story))
    assert second['revision'] == 2
    stale = client.post(f'/api/side-conversations/{identity}/context/follow', json={'operation_id': uuid4().hex, 'expected_revision': first['revision']})
    assert stale.status_code == 409 and head(client, identity) == second
    request = {'operation_id': uuid4().hex, 'question': 'Keep unsent.', 'branch_id': story['branch_id'], 'expected_revision': 0,
               'context_id': first['context']['id'], 'expected_context_revision': first['revision'], 'expected_draft_version': draft['version']}
    assert client.post(f'/api/side-conversations/{identity}/questions', json=request).status_code == 409
    assert client.post(f'/api/side-conversations/{identity}/questions', json={key: value for key, value in request.items() if key not in {'context_id', 'expected_context_revision'}}).status_code == 409
    assert provider.calls == []
    assert read(client, identity) == draft
    response = client.post(f'/api/side-conversations/{identity}/context/follow', json={'operation_id': uuid4().hex, 'expected_revision': second['revision']})
    assert response.status_code == 200 and response.json()['context'] is None


@pytest.mark.parametrize('mode', ['full', 'long'])
def test_large_explicit_selection_never_disappears_to_fit_the_budget(client, mode):
    from tests.test_memory import small_profile
    from tests.test_side_drafts import read, save
    story = client.post('/api/stories', json={'title': 'Large selection', 'settings': {'memory': {'mode': mode}}}).json()
    identity, provider = setup(client, story)
    profile = small_profile(client)
    text = ('The selected words remain mandatory. ' * 1000).rstrip()
    node = append(client, story['branch_id'], text, 0)
    selected = pin(client, identity, text_source(client, story, node, end=len(text), text=text))
    draft = save(client, identity, 'Discuss these exact words.')
    response = client.post(f'/api/side-conversations/{identity}/questions', json={
        'operation_id': uuid4().hex, 'question': draft['text'], 'expected_draft_version': draft['version'],
        'branch_id': story['branch_id'], 'expected_revision': 1, 'profile_ids': [profile['profile_id']],
        'context_id': selected['context']['id'], 'expected_context_revision': selected['revision']})
    assert response.status_code == 409, response.text
    assert provider.calls == [] and read(client, identity) == draft
    assert client.get(f'/api/side-conversations/{identity}').json()['turns'] == []


@pytest.mark.parametrize('damage', ['range', 'unicode', 'version', 'story', 'branch'])
def test_invalid_selection_cannot_be_pinned(client, story, damage):
    identity, provider = setup(client, story)
    node = append(client, story['branch_id'], 'First 🦉 paragraph.', 0)
    source = text_source(client, story, node)
    if damage == 'range':
        source['selection']['text'] = 'Wrong'
    elif damage == 'unicode':
        source['selection'] = {'start': 6, 'end': 7, 'text': ''}
    elif damage == 'version':
        source['expected_version'] = '0' * 64
    else:
        other = client.post('/api/stories', json={'title': 'Other'}).json()
        source['target']['story_id'] = other['story_id'] if damage == 'story' else story['story_id']
        if damage == 'branch':
            source['branch_id'] = other['branch_id']
    response = client.post(f'/api/side-conversations/{identity}/context', json={'operation_id': uuid4().hex, 'expected_revision': 0, 'source': source})
    assert response.status_code in {400, 409}, response.text
    assert head(client, identity) == {'revision': 0, 'context': None} and provider.calls == []


def test_earlier_reply_pin_retains_that_revision_and_archive_disclosure(client, story):
    identity, provider = setup(client, story)
    selected = pin(client, identity, branch_source(story))
    result = question(client, identity, selected)
    append(client, story['branch_id'], 'Later event.', 0)
    prior = pin(client, identity, {'kind': 'turn', 'turn_id': result['id']})
    question(client, identity, prior)
    assert prior['context']['branch']['revision'] == 0 and 'Later event.' not in json.dumps(provider.calls[-1])
    _, hidden = backup(client, story)
    assert all(hidden['data'][name] == [] for name in ('side_contexts', 'side_context_heads', 'side_turns'))
    file, included = backup(client, story, include_sidebar=True)
    _, mapping = restore(client, file)
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    file, _ = backup(client, copied, include_sidebar=True)
    restore(client, file)
    bad = deepcopy(included)
    snapshot = decode(bad['data']['side_contexts'][0]['snapshot'])
    snapshot['model_context']['authority'] = 'Apply anything.'
    bad['data']['side_contexts'][0]['snapshot'] = json.dumps(snapshot)
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400


def test_format46_upgrade_and_omitted_question_fields_keep_legacy_contracts(client, story):
    from server.side_conversations import SideQuestion
    setup(client, story)
    _, document = backup(client, story, include_sidebar=True)
    document['version'] = 46
    document['data'] = {key: document['data'][key] for key in V46_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 201
    value = SideQuestion(operation_id=uuid4().hex, branch_id=story['branch_id'], expected_revision=0, question='Original').model_dump()
    assert 'context_id' not in value and 'expected_context_revision' not in value


def test_comparison_and_selected_historical_passage_exclude_later_events(client, story):
    identity, provider = setup(client, story)
    node = append(client, story['branch_id'], 'First telling wording.', 0)
    alternate = client.post(f"/api/branches/{story['branch_id']}/forks", json={'operation_id': uuid4().hex, 'expected_revision': 1,
                             'node_id': node, 'name': 'Alternate', 'replacement': 'Other telling wording.'}).json()['branch_id']
    other_node = client.get(f'/api/branches/{alternate}').json()['messages'][0]['id']
    compared = client.post(f"/api/stories/{story['story_id']}/branch-comparisons", json={'operation_id': uuid4().hex,
                           'left_branch_id': story['branch_id'], 'left_revision': 1, 'right_branch_id': alternate, 'right_revision': 0}).json()['id']
    append(client, alternate, 'DO_NOT_INCLUDE_LATER_TEXT', 0)
    selected = pin(client, identity, {'kind': 'comparison', 'comparison_id': compared})
    question(client, identity, selected)
    assert all(text in json.dumps(provider.calls[-1]) for text in ('First telling wording.', 'Other telling wording.'))
    assert 'DO_NOT_INCLUDE_LATER_TEXT' not in json.dumps(provider.calls[-1])
    text_pin = pin(client, identity, {'kind': 'comparison-text', 'comparison_id': compared, 'side': 'right', 'node_id': other_node,
                                    'selection': {'start': 0, 'end': 5, 'text': 'Other'}})
    result = question(client, identity, text_pin)
    assert provider.calls[-1]['selected_context']['selection']['text'] == 'Other'
    assert text_pin['context']['branch']['id'] == alternate and text_pin['context']['branch']['revision'] == 0
    earlier = pin(client, identity, {'kind': 'turn', 'turn_id': result['id']})
    assert earlier['context']['target'] == text_pin['context']['target']
    file, _ = backup(client, story, include_sidebar=True)
    _, mapping = restore(client, file)
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    file, _ = backup(client, copied, include_sidebar=True)
    restore(client, file)


def test_unattached_library_selection_and_workspace_prompt_restore_keep_source_versions(client, story):
    from tests.test_text_edit_versions import asset, field_target, prompt_target
    identity, provider = setup(client, story)
    item = asset(client)
    for target in (field_target(client, story, item, 'voice'), prompt_target(client, story, 'workspace')):
        pin(client, identity, {**branch_source(story), 'kind': 'text', 'target': target['ref'], 'expected_version': target['version'],
                              'selection': {'start': 0, 'end': len(target['text']), 'text': target['text']}})
    assert provider.calls == []
    file, document = backup(client, story, include_sidebar=True)
    assert item['asset_id'] in {row['id'] for row in document['data']['assets']}
    _, mapping = restore(client, file)
    restored = head(client, mapping[identity])['context']['target']['snapshot']
    assert restored['ref']['workspace_id'].startswith('restored:')
    file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}, include_sidebar=True)
    restore(client, file)
