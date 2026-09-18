import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.memory.chunks import compile_chunks
from server.memory.packet import assemble_memory, token_estimate
from server.memory.recall import history_corpus, thread_hits
from server.memory.retrieval import Corpus
from tests.test_archives import backup, restore
from tests.test_context_inspector import database_dump, preview, read_section
from tests.test_generations import DraftProvider, WaitingProvider, finished
from tests.test_history import append


def fixture_context(mode='long'):
    opening = 'Mara promised to return the brass observatory key to Ivo before the eclipse.'
    filler = 'The market stalls were quiet. Vendors folded cloth beside the fountain. ' * 12
    texts = [opening, *[f'{filler} Afternoon {index}.' for index in range(40)],
             'Mara reached the observatory with Ivo. The eclipse was beginning.']
    return {'story': {'title': 'The observatory', 'premise': '', 'settings': {'memory': {'mode': mode}}},
            'history': [{'id': f'n{index}', 'role': 'narrator', 'text': text, 'metadata': {}}
                        for index, text in enumerate(texts)],
            'continuity': {'entries': [], 'commits': []}, 'library': [],
            'direction': 'Remember the promise about the observatory key.'}


def profiles(*limits):
    return [{'config': {'context_tokens': limit, 'max_output_tokens': 512}} for limit in limits]


def small_profile(client, name='Writer', limit=4096):
    response = client.post('/api/profiles', json={'name': name, 'make_primary': True,
        'config': {'provider': 'local', 'model': 'test', 'context_tokens': limit, 'max_output_tokens': 512}})
    assert response.status_code == 201, response.text
    return response.json()


def long_story(client):
    response = client.post('/api/stories', json={'title': 'Long path',
        'settings': {'memory': {'mode': 'long'}, 'disabled_prompts': []}})
    assert response.status_code == 201, response.text
    story = response.json()
    texts = fixture_context()['history']
    ids = [append(client, story['branch_id'], node['text'], index) for index, node in enumerate(texts)]
    return story, ids


def test_markdown_chunks_retain_exact_unicode_sources_and_stable_identity():
    text = '# \u00c9l\u00e9onore\n\nA silver key \U0001f511.\n\n## The sealed room\n\n' + '\u96e8 and moonlight. ' * 500
    chunks = compile_chunks('version:v1', 'Notes', text, 'Canon')
    assert ''.join(chunk.text for chunk in chunks) == text
    assert all(len(chunk.text) <= 2400 for chunk in chunks)
    assert all(text[chunk.start:chunk.end] == chunk.text for chunk in chunks)
    assert all(hashlib.sha256(chunk.text.encode()).hexdigest() == chunk.digest for chunk in chunks)
    assert compile_chunks('version:v1', 'Notes', text, 'Canon') == chunks
    assert compile_chunks('version:v2', 'Notes', text, 'Canon')[0].id != chunks[0].id


def test_retrieval_has_no_hits_for_unknown_evidence_and_uses_only_supplied_corpus():
    allowed = compile_chunks('message:allowed', 'Earlier event', '\u00c9l\u00e9onore hid the orchid medallion.')
    foreign = compile_chunks('message:future', 'Later event', 'The orchid medallion belongs to the murderer.')
    Corpus([*allowed, *foreign]).search('orchid murderer')
    restricted = Corpus(allowed)
    assert restricted.search('orbital reactor shutdown') == []
    assert {hit.chunk.source_id for hit in restricted.search('\u00c9l\u00e9onore orchid medallion')} == {'message:allowed'}
    assert 'murderer' not in restricted.df


def test_full_history_is_unchanged_and_long_history_fits_without_mutating_sources():
    full = fixture_context('full')
    packet, receipt = assemble_memory(full, 'Write.', profiles(4096))
    assert packet is full and receipt is None
    original = fixture_context()
    preserved = deepcopy(original)
    packet, receipt = assemble_memory(original, 'Write.', profiles(4096))
    assert original == preserved
    assert packet['history'][-1] == original['history'][-1]
    assert token_estimate('Write.', packet) + receipt['overhead_margin'] <= 4096 - 512
    assert not receipt['coverage']['complete_path']
    assert receipt['coverage']['messages'] == len(original['history'])
    assert any('brass observatory key' in item['text'] for item in packet['recalled_passages'])
    assert packet['recalled_passages'][0]['source_id'] == 'message:n0'
    assert packet['recalled_passages'][0]['passage_number'] == 1



def test_recall_selection_uses_relevance_but_presents_evidence_in_story_order():
    context = fixture_context()
    context['history'][20]['text'] = 'Observatory key promise: Mara returned the brass key to Ivo.'
    context['direction'] = 'Observatory key promise returned brass key.'
    packet, _ = assemble_memory(context, 'Write.', profiles(4096))
    sources = [item['source_id'] for item in packet['recalled_passages']]
    assert 'message:n0' in sources and 'message:n20' in sources
    assert sources.index('message:n0') < sources.index('message:n20')
    positions = [(item['passage_number'], item['start']) for item in packet['recalled_passages']]
    assert positions == sorted(positions)


def test_old_author_notes_are_required_and_never_treated_as_retrieved_events():
    context = fixture_context()
    note = {'id': 'note', 'role': 'ooc', 'text': 'Keep all violence off the page.', 'metadata': {}}
    context['history'].insert(1, note)
    packet, _ = assemble_memory(context, 'Write.', profiles(4096))
    assert note in packet['history']
    assert all(item['source_id'] != 'message:note' for item in packet['recalled_passages'])


def test_open_thread_recall_keeps_unfulfilled_promises_separate_from_instructions():
    context = fixture_context()
    corpus = history_corpus(context['history'], {'n41'})
    entry = {'kind': 'thread', 'status': 'active', 'subject': 'Return the key',
             'text': 'Mara promised Ivo the brass observatory key before the eclipse.'}
    hits = thread_hits(corpus, {'entries': [entry]})
    assert hits[0].chunk.source_id == 'message:n0'
    assert hits[0].reason == 'Open thread: Return the key'
    assert thread_hits(corpus, {'entries': [{**entry, 'status': 'resolved'}]}) == []
    context['continuity']['entries'] = [entry]
    context['direction'] = 'Describe the market.'
    context['story']['settings']['memory']['open_threads'] = False
    _, receipt = assemble_memory(context, 'Write.', profiles(4096))
    assert not any(item['reason'].startswith('Open thread:') for item in receipt['selected'])


def test_comparison_uses_the_smallest_profile_and_is_deterministic():
    context = fixture_context()
    first = assemble_memory(context, 'Write.', profiles(8192, 4096))
    assert first == assemble_memory(context, 'Write.', profiles(4096, 8192))
    assert first[1]['input_allowance'] == 4096 - 512
    assert first == assemble_memory(deepcopy(context), 'Write.', profiles(8192, 4096))


def test_required_material_is_not_silently_clipped():
    context = fixture_context()
    context['story']['premise'] = 'A binding author rule. ' * 2000
    packet, receipt = assemble_memory(context, 'Write.', profiles(4096))
    assert packet['story']['premise'] == context['story']['premise']
    assert token_estimate('Write.', packet) > receipt['input_allowance']


def test_api_preview_is_read_only_and_matches_actual_common_provider_packet(client):
    first = small_profile(client)
    second = small_profile(client, 'Larger', 8192)
    story, ids = long_story(client)
    before = database_dump(client)
    report, body = preview(client, story, expected_revision=len(ids),
                           profile_ids=[first['profile_id'], second['profile_id']],
                           direction='The observatory key promise.')
    assert not report['coverage']['complete_path']
    assert all(budget['fits'] for budget in report['budgets'])
    assert database_dump(client) == before
    section = read_section(client, story, report, body, 'recalled_passages', view='readable')
    assert section.status_code == 200 and 'brass observatory key' in section.json()['text']
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations",
                           json={**body, 'operation_id': uuid4().hex})
    assert response.status_code == 201, response.text
    result = finished(client, response.json()['id'])
    assert result['snapshot']['memory'] == report['memory']
    assert len(provider.calls) == 2 and provider.calls[0][1:] == provider.calls[1][1:]
    assert len(client.get(f"/api/branches/{story['branch_id']}").json()['messages']) == len(ids)


def test_historical_fork_cannot_recall_an_abandoned_future_or_other_story(client):
    small_profile(client)
    story, ids = long_story(client)
    append(client, story['branch_id'], 'FUTURE: The eclipse key opens the murderer vault.', len(ids))
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': len(ids) + 1,
        'node_id': ids[20], 'name': 'Before the revelation'}).json()
    other = client.post('/api/stories', json={'title': 'Unrelated'}).json()
    append(client, other['branch_id'], 'FOREIGN: eclipse key murderer vault.', 0)
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=0, direction='eclipse key murderer vault')
    with client.app.state.database.connect() as connection:
        snapshot, _ = generation_snapshot(connection, fork['branch_id'], body)
    assert 'FUTURE:' not in snapshot['content'] and 'FOREIGN:' not in snapshot['content']
    assert snapshot['coverage']['messages'] == 21


def test_retry_keeps_memory_even_after_story_policy_changes(client):
    small_profile(client)
    story, ids = long_story(client)
    client.app.state.runner.provider = WaitingProvider()
    run = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': len(ids), 'direction': 'The key promise.'}).json()
    candidate = run['candidate_ids'][0]
    client.post(f'/api/candidates/{candidate}/cancel')
    stopped = finished(client, run['id'])
    current = client.get(f"/api/stories/{story['story_id']}").json()
    response = client.put(f"/api/stories/{story['story_id']}", json={
        'expected_revision': current['revision'], 'title': current['title'], 'premise': '',
        'settings': {'memory': {'mode': 'full'}}})
    assert response.status_code == 200
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    assert client.post(f'/api/candidates/{candidate}/retry').status_code == 200
    completed = finished(client, run['id'])
    assert completed['snapshot'] == stopped['snapshot']
    assert provider.calls[0][2] == stopped['snapshot']['content']


def test_archive_restore_keeps_frozen_memory_bytes_and_policy(client):
    small_profile(client)
    story, ids = long_story(client)
    client.app.state.runner.provider = DraftProvider()
    run = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': len(ids), 'direction': 'The key promise.'}).json()
    original = finished(client, run['id'])['snapshot']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    with client.app.state.database.connect() as connection:
        restored = decode(one(connection, 'SELECT snapshot FROM generations WHERE id=?', (mapping[run['id']],))['snapshot'])
    assert restored['content'] == original['content']
    assert restored['memory'] == original['memory']
    restored_story = client.get(f"/api/stories/{mapping[story['story_id']]}").json()
    assert restored_story['settings']['memory']['mode'] == 'long'


@pytest.mark.parametrize('memory', [{'mode': 'invalid'}, {'recall_limit': 1000}, {'unknown': True}])
def test_invalid_memory_settings_are_rejected(client, memory):
    response = client.post('/api/stories', json={'title': 'Invalid', 'settings': {'memory': memory}})
    assert response.status_code == 409
