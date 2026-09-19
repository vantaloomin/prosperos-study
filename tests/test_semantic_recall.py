import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.hybrid_recall import hybrid_hits
from server.memory.semantic_recall import semantic_search
from server.memory.writer_recall import digest
from server.memory.writer_recall_packet import search_sources
from server.providers.config import ProfileConfig
from server.providers.embeddings import embed, parse_embeddings
from server.providers.scheduling import MAINTENANCE, work_scope
from server.providers.service import ProviderService
from tests.test_archives import backup, restore
from tests.test_generations import finished
from tests.test_writer_recall import RecallProvider, change_memory, setup_story, start


class SemanticProvider(RecallProvider):
    def __init__(self, database=None, wait=None):
        super().__init__('{"queries":["fulfilment obligation"]}', wait)
        self.database = database
        self.embedding_calls = []

    async def embed(self, profile, texts):
        self.embedding_calls.append(list(texts))
        if self.wait == 'embed':
            await asyncio.sleep(60)
        if self.wait == 'bad':
            raise ValueError('Invalid fixture embedding response')
        vectors = [[1.0, 0.0] if any(term in text for term in ('parcel', 'courier', 'obligation')) else [0.0, 1.0]
                   for text in texts]
        return {'vectors': vectors, 'model': 'embed-fixture', 'usage': {'total_tokens': len(texts)}}


def configure_semantic(client, story, input_format='plain'):
    change_memory(client, story, semantic_recall=True)
    response = client.post('/api/profiles', json={'name': 'Semantic writer', 'make_primary': True,
        'config': {'provider': 'local', 'model': 'test', 'embedding_model': 'embed-fixture',
                   'embedding_input_format': input_format,
                   'context_tokens': 4096, 'max_output_tokens': 512}})
    assert response.status_code == 201, response.text
    return response.json()


def test_embedding_transport_uses_explicit_model_and_orders_indexes():
    config = ProfileConfig(provider='local', local_protocol='lmstudio', model='writer', embedding_model='embed').model_dump()

    def handler(request):
        assert request.url.path == '/v1/embeddings'
        assert json.loads(request.content) == {'model': 'embed', 'input': ['alpha', 'beta'], 'encoding_format': 'float'}
        return httpx.Response(200, json={'model': 'embed', 'data': [
            {'index': 1, 'embedding': [0, 2]}, {'index': 0, 'embedding': [3, 0]}]})

    result = asyncio.run(embed(config, None, ['alpha', 'beta'], httpx.MockTransport(handler)))
    assert result['vectors'] == [[1, 0], [0, 1]]


@pytest.mark.parametrize('rows', [
    [{'index': 0, 'embedding': [0, 0]}], [{'index': 0, 'embedding': [True]}],
    [{'index': 0, 'embedding': [float('nan')]}], [{'index': 1, 'embedding': [1]}],
    [{'index': 0, 'embedding': 'invalid'}], []])
def test_invalid_embedding_responses_cannot_become_search_results(rows):
    with pytest.raises(DomainError):
        parse_embeddings({'data': rows}, 1, 'embedding')


def test_semantic_hit_is_not_limited_to_lexical_candidates():
    sources = [{'id': f'c{i}', 'source_id': f'm{i}', 'title': '', 'text': text, 'start': 0, 'end': len(text),
                'sha256': digest(text), 'kind': 'accepted passage'}
               for i, text in enumerate(['A brass key.', 'The undertaking was fulfilled.'])]
    query = ['successful delivery']
    assert not search_sources(sources, query)
    semantic = {'rankings': [[{'id': 'c1', 'sha256': sources[1]['sha256'], 'score': 0.9}]]}
    hits = hybrid_hits(sources, query, semantic)
    assert [hit.chunk.id for hit in hits] == ['c1'] and not hits[0].matched


def test_cache_warms_in_bounded_batches_and_invalidates_changed_source_and_profile(tmp_path):
    provider = SemanticProvider(SimpleNamespace(path=tmp_path / 'story.sqlite3'))
    sources = [{'id': f'c{i}', 'sha256': digest(f'prose {i}'), 'text': f'prose {i}'} for i in range(75)]
    snapshot = {'writer_recall': {'semantic': {'enabled': True}, 'sources': sources}}
    profile = {'number': 1, 'config': ProfileConfig(provider='local', model='writer', embedding_model='embed-fixture').model_dump()}

    def run():
        return asyncio.run(semantic_search(provider, profile, snapshot, ['obligation'], {}, lambda: None))

    first = run()
    assert first['status'] == 'fallback' and first['new_sources'] == 64 and first['calls'] == 4
    second = run()
    assert second['status'] == 'completed' and second['cache_hits'] == 64 and second['new_sources'] == 11 and second['calls'] == 2
    sources[0] = {'id': 'changed', 'sha256': digest('changed prose'), 'text': 'changed prose'}
    third = run()
    assert third['cache_hits'] == 74 and third['new_sources'] == 1
    profile['number'] = 2
    assert run()['new_sources'] == 64


@pytest.mark.parametrize('input_format', ['plain', 'nomic-search-v1'])
def test_semantic_writer_receipt_replays_and_restores_without_reembedding(client, input_format):
    story, nodes = setup_story(client)
    configure_semantic(client, story, input_format)
    provider = SemanticProvider(client.app.state.database, wait='write')
    client.app.state.runner.provider = provider
    run = start(client, story, len(nodes))
    for _ in range(100):
        detail = client.get(f"/api/generations/{run['id']}").json()
        if detail['candidates'][0]['output']:
            break
    candidate = detail['candidates'][0]
    assert candidate['output'] == 'An unfinished draft.'
    receipt = candidate['usage']['writer_recall']
    semantic = receipt['semantic']
    assert semantic['status'] == 'completed' and semantic['total_sources'] == 18 and semantic['calls'] == 3
    assert semantic['identity'].get('input_format', 'plain') == input_format
    if input_format == 'nomic-search-v1':
        assert all(text.startswith('search_document: ') for batch in provider.embedding_calls[:-1] for text in batch)
        assert all(text.startswith('search_query: ') for text in provider.embedding_calls[-1])
    assert all(text in receipt['final_input']['content'] for text in ('promised to return', 'handed the copper parcel', 'Delivery had failed'))
    assert client.post(f"/api/candidates/{candidate['id']}/cancel").status_code == 200
    finished(client, run['id'])
    provider.wait = None
    assert client.post(f"/api/candidates/{candidate['id']}/retry").status_code == 200
    done = finished(client, run['id'])
    assert done['candidates'][0]['usage']['writer_recall'] == receipt and len(provider.embedding_calls) == 3
    file, archive = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['candidates'][0]['usage']['writer_recall'] == receipt
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    changed = deepcopy(archive)
    row = changed['data']['candidates'][0]
    usage = decode(row['usage'])
    usage['writer_recall']['semantic']['rankings'][0][0]['id'] = 'sibling-source'
    row['usage'] = encode(usage)
    with pytest.raises(DomainError):
        parse_archive(encode(changed))


@pytest.mark.parametrize('configured', [True, False])
def test_semantic_failure_retains_keyword_search_and_reports_cost(client, configured):
    story, nodes = setup_story(client)
    if configured:
        configure_semantic(client, story)
    else:
        change_memory(client, story, semantic_recall=True)
    provider = SemanticProvider(wait='bad')
    provider.output = '{"queries":["copper parcel courier ravine"]}'
    client.app.state.runner.provider = provider
    done = finished(client, start(client, story, len(nodes))['id'])
    receipt = done['candidates'][0]['usage']['writer_recall']
    assert receipt['status'] == 'completed' and receipt['semantic']['status'] == 'fallback'
    assert receipt['semantic']['calls'] == int(configured)
    assert 'Delivery had failed' in receipt['final_input']['content']
    assert len(provider.calls) == 2
    backup(client, story)


def test_cancelling_embeddings_never_starts_writer(client):
    story, nodes = setup_story(client)
    configure_semantic(client, story)
    provider = SemanticProvider(wait='embed')
    client.app.state.runner.provider = provider
    run = start(client, story, len(nodes))
    for _ in range(100):
        client.get(f"/api/generations/{run['id']}")
        if provider.embedding_calls:
            break
    assert provider.embedding_calls
    candidate_id = run['candidate_ids'][0]
    assert client.post(f'/api/candidates/{candidate_id}/cancel').status_code == 200
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'cancelled' and candidate['output'] == '' and len(provider.calls) == 1
    assert candidate['usage']['writer_recall']['semantic']['status'] == 'cancelled'
    assert candidate['activity']['first_text_at'] is None
    backup(client, story)


def test_embedding_adapter_cannot_run_as_unverified_background_work():
    service = ProviderService(None)

    async def run():
        with work_scope(MAINTENANCE), pytest.raises(DomainError, match='automatic background'):
            await service.embed({'config': {}}, ['text'])

    asyncio.run(run())
