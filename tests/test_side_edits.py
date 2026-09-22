import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import many
from server.providers.events import ProviderEvent
from server.text_edits.selection import whole_text
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_profiles import make_profile
from tests.test_side_targets import pin
from tests.test_sidebar import settle, thread
from tests.test_text_edits import apply, proposal, save_document, target, undo


class Provider:
    def __init__(self, output=None, complete=True, finish=None, hold=False, uncertain=False):
        self.output = output or {'replacement': '  Revised 🦉 wording.\n', 'explanation': 'Keep the uncertainty.', 'source_ids': []}
        self.complete, self.finish, self.hold = complete, finish, hold
        self.uncertain = uncertain
        self.calls = []
        self.release = None

    async def generate(self, profile, prompt, content):
        self.calls.append((deepcopy(profile), prompt, json.loads(content)))
        yield ProviderEvent(text=json.dumps(self.output) if isinstance(self.output, dict) else self.output)
        if self.hold:
            self.release = asyncio.Event()
            await self.release.wait()
        if self.complete:
            yield ProviderEvent(done=True, usage={**({'finish_reason': self.finish} if self.finish else {}),
                                                 **({'output_limit_uncertain': True} if self.uncertain else {})})


def setup(client, story, source=None, provider=None):
    make_profile(client, 'Scoped Companion fixture', primary=True)
    identity = thread(client, story)
    source = source or target(client, {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': 'composer'})
    if not source['text']:
        source = save_document(client, source, 'Original wording.') if source['ref']['kind'] == 'document' else apply(client, proposal(client, source, 'Original wording.'))['after_target']
    selected = pin(client, identity, {'kind': 'text', 'branch_id': story['branch_id'], 'expected_revision': client.get(f"/api/branches/{story['branch_id']}").json()['revision'],
                                    'target': source['ref'], 'expected_version': source['version'], 'selection': whole_text(source['text'][:8])})
    client.app.state.side_runner.provider = provider or Provider()
    return identity, source, selected


def ask(client, identity, selected, work=None):
    context = selected['context']
    body = {'operation_id': uuid4().hex, 'question': 'Private author instruction: revise only the selected text.',
            'branch_id': context['branch']['id'], 'expected_revision': context['branch']['revision'],
            'context_id': context['id'], 'expected_context_revision': selected['revision'],
            'work': work or {'task': 'rewrite'}}
    response = client.post(f'/api/side-conversations/{identity}/questions', json=body)
    assert response.status_code == 201, response.text
    assert client.post(f'/api/side-conversations/{identity}/questions', json=body).json() == response.json()
    return response.json()


def reply(client, identity):
    return client.get(f'/api/side-conversations/{identity}').json()['turns'][-1]['replies'][-1]


@pytest.mark.parametrize('mode', ['full', 'long'])
def test_generated_suggestion_edits_apply_undo_and_repeated_restore_preserve_original_request(client, mode):
    story = client.post('/api/stories', json={'title': 'Scoped edits', 'settings': {'memory': {'mode': mode}}}).json()
    identity, source, selected = setup(client, story)
    ask(client, identity, selected)
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'done', response['error']
    assert target(client, source['ref']) == source
    edit = response['edit']['proposals'][0]
    changed = client.patch(f"/api/text-edits/{edit['id']}", json={'operation_id': uuid4().hex, 'expected_revision': 0,
                           'replacement': 'Reviewed', 'explanation': 'An author correction.'}).json()
    receipt = apply(client, changed)
    assert receipt['after_target']['text'] == 'Reviewed wording.'
    undo(client, receipt)
    assert target(client, source['ref'])['text'] == source['text']
    inputs = client.get(f"/api/side-replies/{response['id']}/requests/0").json()
    assert json.loads(inputs['content'])['companion_task']['action'] == 'replace'
    original_output = response['output']
    for private in (False, True):
        file, document = backup(client, story, include_sidebar=private)
        assert len(document['data']['companion_edit_origins']) == 1
        assert bool(document['data']['side_edit_results']) == private
        if not private:
            assert 'Private author instruction:' not in json.dumps(document)
        _, mapping = restore(client, file)
        copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
        second, _ = backup(client, copied, include_sidebar=private)
        restore(client, second)
        if private:
            restored = reply(client, mapping[identity])
            assert restored['output'] == original_output
            assert client.get(f"/api/side-replies/{restored['id']}/requests/0").json()['content'] == inputs['content']


@pytest.mark.parametrize('action', ['replace', 'insert-before', 'insert-after', 'add', 'update'])
def test_author_application_uses_only_the_recorded_text_action_and_is_idempotent(client, story, action):
    identity, source, selected = setup(client, story)
    ask(client, identity, selected, {'task': 'write', 'authority': 'apply', 'action': action})
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'done', response['error']
    edit = response['edit']['proposals'][0]
    receipt = edit['receipt']
    assert receipt and edit['status'] == 'applied'
    assert receipt['action'] == action and target(client, source['ref'])['text'] == edit['after_text']
    assert apply(client, edit)['id'] == receipt['id']
    assert len(client.app.state.side_runner.provider.calls) == 1
    with client.app.state.database.connect() as connection:
        assert len(many(connection, 'SELECT * FROM companion_edit_origins')) == 1
        assert len(many(connection, 'SELECT * FROM text_edit_receipts')) == 1


@pytest.mark.parametrize('damage', ['extra-target', 'scope', 'empty', 'partial', 'length', 'uncertain'])
def test_model_output_cannot_expand_authority_or_apply_incomplete_text(client, story, damage):
    provider = Provider()
    if damage == 'extra-target':
        provider.output['target'] = {'kind': 'story-brief', 'story_id': story['story_id']}
    elif damage == 'scope':
        provider.output['source_ids'] = ['not-an-allowed-source']
    elif damage == 'empty':
        provider.output = 'not structured output'
    elif damage == 'partial':
        provider.complete = False
    elif damage == 'uncertain':
        provider.uncertain = True
    else:
        provider.finish = 'length'
    identity, source, selected = setup(client, story, provider=provider)
    ask(client, identity, selected, {'task': 'rewrite', 'authority': 'apply'})
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'error' and response['edit'] is None and response['output']
    assert target(client, source['ref']) == source


@pytest.mark.parametrize('cancel', [False, True])
def test_changed_target_or_cancellation_during_generation_cannot_overwrite_newer_text(client, story, cancel):
    provider = Provider(hold=True)
    identity, source, selected = setup(client, story, provider=provider)
    request = ask(client, identity, selected, {'task': 'rewrite', 'authority': 'apply'})
    async def ready():
        while provider.release is None:
            await asyncio.sleep(0.01)
    client.portal.call(ready)
    current = save_document(client, source, 'Independent later words.')
    if cancel:
        assert client.post(f"/api/side-replies/{request['reply_ids'][0]}/cancel").status_code == 200
    else:
        client.portal.call(provider.release.set)
    settle(client)
    response = reply(client, identity)
    assert target(client, source['ref']) == current
    if cancel:
        assert response['status'] == 'cancelled' and response['edit'] is None
    else:
        assert response['status'] == 'done' and response['edit']['error']
        assert response['edit']['proposals'][0]['status'] == 'conflict'
        assert response['edit']['proposals'][0]['receipt'] is None


def test_explicit_accepted_passage_application_preserves_the_original_suffix_and_undo(client, story):
    node = append(client, story['branch_id'], 'Original passage.', 0)
    append(client, story['branch_id'], 'A later passage.', 1)
    source = target(client, {'kind': 'passage', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'node_id': node})
    identity, source, selected = setup(client, story, source)
    ask(client, identity, selected, {'task': 'rewrite', 'authority': 'apply'})
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'done', response['error']
    receipt = response['edit']['proposals'][0]['receipt']
    assert receipt and receipt['after_target']['ref']['branch_id'] != story['branch_id']
    original = client.get(f"/api/branches/{story['branch_id']}").json()
    revised = client.get(f"/api/branches/{receipt['after_target']['ref']['branch_id']}").json()
    assert original['messages'][0]['text'] == 'Original passage.' and revised['messages'][-1]['text'] == 'A later passage.'
    undo(client, receipt)
    file, _ = backup(client, story, include_sidebar=True)
    restore(client, file)


def test_discussion_tasks_never_receive_style_or_apply_permissions(client, story):
    identity, source, selected = setup(client, story, provider=Provider(output='A factual discussion.'))
    ask(client, identity, selected, {'task': 'check-continuity'})
    settle(client)
    assert reply(client, identity)['edit'] is None
    assert 'writing_guidance' not in client.app.state.side_runner.provider.calls[0][2]
    assert target(client, source['ref']) == source


def test_saved_style_and_revision_recipe_are_frozen_for_explicit_retry_and_restore(client, story):
    from tests.test_writing_resources import create
    style = create(client, content={'prose': 'Use spare, concrete wording.', 'examples': [{'label': 'Pacing example', 'text': 'Only the lamp remained.'}]})
    recipe = create(client, 'recipe', {'purpose': 'revise', 'instructions': 'Preserve {{detail}}.', 'style': style['id'],
                                     'variables': [{'name': 'detail', 'label': 'Detail', 'type': 'text'}],
                                     'steps': [{'task': 'revision', 'instructions': 'Keep dialogue intact.'}]}, 'Dialogue pass')
    provider = Provider(output='Malformed first response')
    identity, source, selected = setup(client, story, provider=provider)
    ask(client, identity, selected, {'task': 'apply-style', 'writing': {'recipe': recipe['id'], 'variables': {'detail': 'the sealed letter'}}})
    settle(client)
    first = reply(client, identity)
    frozen = provider.calls[0][2]
    assert frozen['writing_guidance']['style']['id'] == style['id']
    assert frozen['writing_guidance']['resolved_recipe']['instructions'] == 'Preserve the sealed letter.'
    assert frozen['writing_guidance']['style']['content']['examples'][0]['text'] == 'Only the lamp remained.'
    published = client.post(f"/api/writing-resources/{style['asset_id']}/versions", json={'operation_id': uuid4().hex, 'kind': 'style', 'name': 'Later style',
                            'content': {'prose': 'More expansive.'}, 'expected_version_id': style['id']})
    assert published.status_code == 201, published.text
    provider.output = {'replacement': 'A spare revision', 'explanation': 'Use the chosen pacing.', 'source_ids': []}
    assert client.post(f"/api/side-replies/{first['id']}/retry").status_code == 201
    settle(client)
    assert provider.calls[-1][1:] == provider.calls[0][1:]
    assert reply(client, identity)['edit']['origin']['writing']['style']['name'] == style['name']
    file, _ = backup(client, story, include_sidebar=True)
    _, mapping = restore(client, file)
    copied = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    second, _ = backup(client, copied, include_sidebar=True)
    restore(client, second)
    assert target(client, source['ref']) == source


@pytest.mark.parametrize('damage', ['authority', 'target', 'selection', 'output', 'completion'])
def test_tampered_scoped_edit_provenance_is_rejected(client, story, damage):
    from server.database import decode, encode
    identity, _, selected = setup(client, story)
    ask(client, identity, selected)
    settle(client)
    _, document = backup(client, story, include_sidebar=True)
    if damage == 'output':
        document['data']['side_replies'][0]['output'] = json.dumps({'replacement': 'Changed', 'explanation': '', 'source_ids': []})
    elif damage == 'completion':
        usage = decode(document['data']['side_replies'][0]['usage'])
        usage[0]['completed'] = False
        document['data']['side_replies'][0]['usage'] = encode(usage)
    else:
        row = document['data']['companion_edit_origins'][0]
        value = decode(row['detail'])
        if damage == 'authority':
            value['request']['authority'] = 'apply'
        elif damage == 'target':
            value['target']['ref']['purpose'] = 'author-note'
        else:
            value['request']['selection']['start'] = 2
        row['detail'] = encode(value)
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code in {400, 409}


def test_format47_cannot_smuggle_scoped_work_and_omitted_field_keeps_legacy_shape(client, story):
    from server.archives.format import V47_TABLES
    from server.side_conversations import SideQuestion
    identity, _, selected = setup(client, story)
    file, document = backup(client, story, include_sidebar=True)
    document['version'] = 47
    document['data'] = {key: document['data'][key] for key in V47_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 201
    assert 'work' not in SideQuestion(operation_id=uuid4().hex, question='Old shape', branch_id=story['branch_id'], expected_revision=0).model_dump()
    ask(client, identity, selected)
    settle(client)
    _, document = backup(client, story, include_sidebar=True)
    document['version'] = 47
    document['data'] = {key: document['data'][key] for key in V47_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


@pytest.mark.parametrize('kind', ['character', 'canon', 'style', 'recipe', 'prompt', 'brief', 'author-note', 'scene-goal', 'candidate', 'scene-block'])
def test_generated_application_uses_existing_versioned_and_draft_destination_contracts(client, story, kind):
    from tests.test_candidate_text_edits import fixture
    from tests.test_scene_reviews import reviewable_plan
    from tests.test_scene_text_edits import source as scene_source
    from tests.test_text_edit_versions import asset, field_target, prompt_target
    from tests.test_writing_resources import create
    if kind in {'character', 'canon'}:
        source = field_target(client, story, asset(client, 'character' if kind == 'character' else 'lorebook'))
    elif kind in {'style', 'recipe'}:
        item = create(client, kind, {'prose': 'Original guidance.'} if kind == 'style' else {'purpose': 'revise', 'instructions': 'Original instructions.'})
        source = field_target(client, story, item, 'prose' if kind == 'style' else 'instructions', kind='writing-field')
    elif kind == 'prompt':
        source = prompt_target(client, story)
    elif kind == 'brief':
        source = target(client, {'kind': 'story-brief', 'story_id': story['story_id']})
    elif kind in {'author-note', 'scene-goal'}:
        source = target(client, {'kind': 'document', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'purpose': kind})
    elif kind == 'candidate':
        _, _, _, source = fixture(client, story)
    else:
        scene, _ = reviewable_plan(client, story, dialogue=True)
        source = scene_source(client, scene)
    identity, source, selected = setup(client, story, source)
    original_messages = client.get(f"/api/branches/{story['branch_id']}").json()['messages']
    ask(client, identity, selected, {'task': 'rewrite', 'authority': 'apply', 'action': 'update', 'writing': {'style': 'none', 'recipe': 'none'}})
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'done', response['error']
    receipt = response['edit']['proposals'][0]['receipt']
    assert receipt, response['edit']['error']
    assert receipt['after_target']['text'] == '  Revised 🦉 wording.\n'
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == original_messages
    file, _ = backup(client, story, include_sidebar=True)
    restore(client, file)
