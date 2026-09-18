import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.errors import DomainError
from server.memory.budget import token_estimate
from server.memory.side_archive import classify_archive, permitted_sources
from server.memory.side_packet import next_packet, prepare_archive
from server.memory.side_search import SourceArchive, command
from server.providers.events import ProviderEvent
from server.side_context import document_parts
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_memory import long_story, profiles, small_profile
from tests.test_sidebar import ask, settle, story_state, thread


def archive_fixture(count=1000):
    documents = [{'id': f'branch:message:n{index}:1', 'title': f'Main path · message {index + 1} · narrator',
                  'text': f'Passage {index}. ' + 'An ordinary street stretches past quiet houses. ' * 20}
                 for index in range(count)]
    documents[0]['text'] = 'The moonstone key belongs to Elin. ' + '\u96e8\U0001f511 ' * 2000
    return {'question': 'Who owns the moonstone key?', 'disclosure': 'spoiler-conscious',
            'conversation': [], 'prompt': {'template': 'Discuss without changing the Story.'},
            'sources': documents, 'max_reads': 4}


def test_large_catalog_is_bounded_and_all_exact_text_remains_reachable_by_ranges():
    original = archive_fixture(3000)
    preserved = deepcopy(original)
    snapshot = prepare_archive(original, [], profiles(4096, 8192))
    assert original == preserved and len(snapshot['sources']) == 3000
    context = decode(snapshot['retrieval']['initial_content'])
    assert len(context['source_index']) <= 8 and context['archive_source_count'] == 3000
    assert token_estimate(snapshot['prompt']['template'], context) <= 4096 - 512 - snapshot['retrieval']['overhead_margin']
    archive = SourceArchive(snapshot)
    source_id, original_text = original['sources'][0]['id'], original['sources'][0]['text']
    restored, offset = '', 0
    while offset < len(original_text):
        packet = decode(next_packet(snapshot, archive, command('READ_SOURCES: ' + encode([{'id': source_id, 'offset': offset, 'length': 700}]))))
        source = packet['sources'][0]
        assert source['start'] == offset and source['sha256'] == hashlib.sha256(source['text'].encode()).hexdigest()
        restored += source['text']
        offset = source['end']
    assert restored == original_text
    last_page = decode(next_packet(snapshot, archive, command('LIST_SOURCES: {"offset":2992}')))
    assert len(last_page['source_index']) == 8 and last_page['discovery']['next_offset'] is None


def test_discovery_scopes_private_background_and_embedded_copies_before_ranking_and_counts():
    snapshot = archive_fixture(10)
    hidden = 'The private sapphire_password is buried under the stage.'
    nested = encode({'snapshot': encode({'content': encode({'private_background': {'secret': hidden}})})})
    snapshot['sources'].extend(document_parts('scene:private', 'A saved plan', nested * 1))
    snapshot['sources'].extend(document_parts('background:secret', 'PRIVATE setup', hidden))
    snapshot['sources'].extend(document_parts('private-interpretation:secret', 'PRIVATE interpretation', hidden))
    scoped = prepare_archive(snapshot, [], profiles(4096))
    assert len(scoped['sources']) == 13 and len(permitted_sources(scoped)) == 10
    archive = SourceArchive(scoped)
    assert archive.search('sapphire_password')['total'] == 0
    assert 'sapphire_password' not in archive.corpus.df
    assert hidden not in scoped['retrieval']['initial_content']
    with pytest.raises(DomainError, match='permitted frozen archive'):
        archive.read([{'id': 'background:secret:1', 'offset': 0, 'length': 100}])
    full = prepare_archive({**snapshot, 'disclosure': 'full-disclosure'}, [], profiles(4096))
    assert len(permitted_sources(full)) == 13
    assert SourceArchive(full).search('sapphire_password')['total'] == 3


def test_private_classification_covers_all_parts_even_when_only_first_part_has_marker():
    text = encode({'private_background': {'secret': 'HIDDEN_VALUE'}, 'large': 'public looking filler ' * 2000})
    chunks = classify_archive(document_parts('run:large', 'Writer request', text))
    assert len(chunks) > 3 and all(item['private'] for item in chunks)


def test_side_discussion_is_archived_but_bounded_and_disclosure_downgrade_excludes_private_turns():
    original = archive_fixture(10)
    history = [{'id': f't{index}', 'question': 'A previous idea.', 'output': 'Long discussion. ' * 1000,
                'snapshot': encode({'branch': {'name': 'Main'}, 'disclosure': 'spoiler-conscious'})} for index in range(20)]
    history.append({'id': 'hidden', 'question': 'Private question.', 'output': 'HIDDENTURNONLY',
                    'snapshot': encode({'branch': {'name': 'Main'}, 'disclosure': 'full-disclosure'})})
    snapshot = prepare_archive(original, history, profiles(4096))
    context = decode(snapshot['retrieval']['initial_content'])
    assert context['conversation'] == []
    assert context['conversation_coverage']['available_turns'] == 20
    assert all(item['authority'].startswith('Side discussion') for item in permitted_sources(snapshot) if item['id'].startswith('discussion:'))
    assert SourceArchive(snapshot).search('HIDDENTURNONLY')['total'] == 0
    assert SourceArchive(snapshot).search('discussion')['total'] > 0
    assert all('HIDDENTURNONLY' not in item['text'] for item in permitted_sources(snapshot))


@pytest.mark.parametrize('output', ['READ_SOURCES: ["file:///passwords"]', 'READ_SOURCES: [{"id":"x","offset":-1}]',
    'READ_SOURCES: [{"id":"x","length":2401}]', 'SEARCH_SOURCES: {"query":"x","shell":"run"}',
    'LIST_SOURCES: {"offset":true}', 'SEARCH_SOURCES: null', 'READ_SOURCES: []'])
def test_archive_commands_reject_foreign_sources_or_unsupported_operations(output):
    snapshot = prepare_archive(archive_fixture(2), [], profiles(4096))
    with pytest.raises(DomainError):
        next_packet(snapshot, SourceArchive(snapshot), command(output))


class SearchReader:
    def __init__(self):
        self.calls = []
        self.prompts = []

    async def generate(self, _profile, _prompt, content):
        context = decode(content)
        self.calls.append(context)
        self.prompts.append(_prompt)
        if context['sources']:
            yield ProviderEvent(text='Proposal only. Evidence: ' + context['sources'][0]['text'], done=True)
        elif context['discovery']['query'] != 'observatory key':
            yield ProviderEvent(text='SEARCH_SOURCES: {"query":"observatory key"}', done=True)
        else:
            source = context['source_index'][0]
            yield ProviderEvent(text='READ_SOURCES: ' + encode([{'id': source['id'], 'offset': 0, 'length': 200}]), done=True)


def test_sidebar_search_records_exact_per_call_inputs_and_cannot_progress_story(client):
    small_profile(client, limit=8192)
    story, nodes = long_story(client)
    provider = SearchReader()
    client.app.state.side_runner.provider = provider
    conversation = thread(client, story)
    before = story_state(client)
    turn = ask(client, conversation, story, revision=len(nodes), question='Discuss the unresolved promise.')
    settle(client)
    detail = client.get(f'/api/side-conversations/{conversation}').json()['turns'][0]
    reply = detail['replies'][0]
    assert reply['status'] == 'done', reply['error']
    assert len(provider.calls) == len(reply['usage']) == 3
    for index, call in enumerate(provider.calls):
        assert 'content' not in reply['usage'][index]
        receipt = client.get(f"/api/side-replies/{reply['id']}/requests/{index}").json()
        assert receipt['prompt'] == provider.prompts[index]
        assert decode(receipt['content']) == call
        assert hashlib.sha256(receipt['content'].encode()).hexdigest() == receipt['content_sha256']
        assert receipt['source_ids'] == list(dict.fromkeys(item['id'] for item in [*call['source_index'], *call['sources']]))
    assert len(provider.calls[-1]['sources']) == 1 and provider.calls[-1]['source_index'] == []
    assert story_state(client) == before
    assert client.post(f"/api/candidates/{reply['id']}/accept", json={'operation_id': uuid4().hex}).status_code == 404
    append(client, story['branch_id'], 'FUTURE AFTER THE FROZEN QUESTION.', len(nodes))
    search = client.get(f"/api/side-turns/{turn['id']}/source-search", params={'query': 'FUTURE AFTER THE FROZEN QUESTION'}).json()
    assert all('FUTURE AFTER' not in item['text'] for item in search['results'])
    archive, _ = backup(client, story, include_sidebar=True)
    restored, mapping = restore(client, archive)
    copied = client.get(f"/api/side-replies/{mapping[reply['id']]}/requests/2").json()
    assert copied == client.get(f"/api/side-replies/{reply['id']}/requests/2").json()
    second, _ = backup(client, {'story_id': restored['story_ids'][0], 'branch_id': mapping[story['branch_id']]}, include_sidebar=True)
    restore(client, second)


def test_long_sidebar_comparison_has_identical_initial_packet_with_different_model_limits(client):
    first = small_profile(client, 'A', 4096)
    second = small_profile(client, 'B', 8192)
    story, nodes = long_story(client)
    from tests.test_sidebar import CollaboratorProvider
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    conversation = thread(client, story)
    ask(client, conversation, story, revision=len(nodes), profile_ids=[first['profile_id'], second['profile_id']])
    settle(client)
    assert provider.calls[0] == provider.calls[1]
    replies = client.get(f'/api/side-conversations/{conversation}').json()['turns'][0]['replies']
    assert all(reply['status'] == 'done' for reply in replies)


def test_legacy_discussion_that_read_private_sources_requires_full_disclosure():
    old = {'branch': {'name': 'Main'}, 'disclosure': 'spoiler-conscious',
           'sources': document_parts('background:old', 'PRIVATE background', 'HIDDEN LEGACY KNOWLEDGE')}
    row = {'id': 'earlier', 'question': 'Explain the plan.', 'output': 'HIDDEN LEGACY KNOWLEDGE',
           'snapshot': encode(old), 'coverage': encode(['background:old:1'])}
    snapshot = prepare_archive(archive_fixture(2), [row], profiles(4096))
    assert snapshot['retrieval']['conversation'] == []
    assert not any('HIDDEN LEGACY' in item['text'] for item in permitted_sources(snapshot))
    full = prepare_archive({**archive_fixture(2), 'disclosure': 'full-disclosure'}, [row], profiles(4096))
    assert full['retrieval']['conversation'][0]['answer'] == 'HIDDEN LEGACY KNOWLEDGE'


@pytest.mark.parametrize('corruption', ['text', 'foreign-source', 'coverage', 'receipt-hash'])
def test_archive_validation_rejects_corrupt_sidebar_reads(corruption):
    from server.archives.side_memory import validate_side_memory
    from server.memory.side_packet import request_receipt
    snapshot = prepare_archive(archive_fixture(5), [], profiles(4096))
    content = snapshot['retrieval']['initial_content']
    receipt = request_receipt(content)
    data = {'side_turns': [{'id': 'turn', 'snapshot': encode(snapshot)}],
            'side_replies': [{'turn_id': 'turn', 'usage': encode([receipt]), 'coverage': encode(sorted(receipt['source_ids']))}]}
    validate_side_memory(data)
    if corruption in {'text', 'foreign-source'}:
        context = decode(content)
        first = context['source_index'][0]
        if corruption == 'text':
            first['text'] = 'Invented evidence.'
            first['sha256'] = hashlib.sha256(first['text'].encode()).hexdigest()
        else:
            first['id'] = 'foreign:secret:1'
        content = encode(context)
        snapshot['retrieval']['initial_content'] = content
        data['side_turns'][0]['snapshot'] = encode(snapshot)
        data['side_replies'][0]['usage'] = encode([request_receipt(content)])
    elif corruption == 'coverage':
        data['side_replies'][0]['coverage'] = '[]'
    else:
        receipt['content_sha256'] = '0' * 64
        data['side_replies'][0]['usage'] = encode([receipt])
    with pytest.raises(DomainError):
        validate_side_memory(data)


def test_stopped_long_sidebar_retry_keeps_original_packet_after_story_and_prompt_changes(client):
    from tests.test_sidebar import CollaboratorProvider, SlowCollaborator
    small_profile(client, limit=8192)
    story, nodes = long_story(client)
    conversation = thread(client, story)
    client.app.state.side_runner.provider = SlowCollaborator()
    turn = ask(client, conversation, story, revision=len(nodes))
    reply_id = turn['reply_ids'][0]
    assert client.post(f'/api/side-replies/{reply_id}/cancel').status_code == 200
    settle(client)
    original = client.get(f'/api/side-replies/{reply_id}/requests/0').json()
    append(client, story['branch_id'], 'Future material must not enter a retry.', len(nodes))
    prompt = next(item for item in client.get('/api/prompts').json() if item['key'] == 'collaborator')
    changed = client.put('/api/prompts/collaborator', json={'expected_version_id': prompt['id'], 'template': 'A newly edited collaborator prompt.'})
    assert changed.status_code == 200
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    retried = client.post(f'/api/side-replies/{reply_id}/retry')
    assert retried.status_code == 201, retried.text
    settle(client)
    assert provider.calls == [decode(original['content'])]
    final = client.get(f'/api/side-conversations/{conversation}').json()['turns'][0]
    assert [item['status'] for item in final['replies']] == ['cancelled', 'done']
    assert final['replies'][0]['output'] == 'An unfinished thought.'


def test_read_limit_is_explicit_and_unknown_ranges_make_no_story_change(client):
    small_profile(client, limit=8192)
    story, nodes = long_story(client)
    client.app.state.side_runner.provider = SearchReader()
    conversation = thread(client, story)
    before = story_state(client)
    ask(client, conversation, story, revision=len(nodes), max_reads=0)
    settle(client)
    reply = client.get(f'/api/side-conversations/{conversation}').json()['turns'][0]['replies'][0]
    assert reply['status'] == 'error' and 'limit was reached' in reply['error']
    assert len(reply['usage']) == 1 and story_state(client) == before


def test_discovery_excerpt_shows_the_rare_match_in_a_long_source():
    original = archive_fixture(3)
    original['sources'][0]['text'] = 'Ordinary background. ' * 80 + 'The zinnialocket contains the map.' + ' More background.' * 300
    snapshot = prepare_archive(original, [], profiles(4096))
    result = SourceArchive(snapshot).search('zinnialocket')['results'][0]
    assert 'zinnialocket' in result['text'] and result['start'] > 0
    assert original['sources'][0]['text'][result['start']:result['end']] == result['text']
