import asyncio
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from scripts.narrative_fresh_cases import freeze
from scripts.narrative_reliability import load
from server.errors import DomainError
from server.memory.semantic_cache import embedding_identity
from server.memory.semantic_recall import semantic_search
from server.memory.writer_recall import digest
from server.providers.config import ProfileConfig
from server.providers.embeddings import embed
from tests.test_semantic_recall import SemanticProvider


def test_fresh_pairs_supply_identical_evidence_without_review_labels(tmp_path):
    directory = tmp_path / 'frozen'
    freeze(directory)
    manifest = load(directory / 'manifest.json')
    assert hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest() == (directory / 'manifest.sha256').read_text()
    assert len(manifest['cases']) == 4
    for row in manifest['cases']:
        assert row['review_note'] not in row['content']
        assert row['case'] not in row['content']
        assert row['candidate_prompt'].startswith(row['baseline_prompt'])
        assert json.loads(row['content'])['history']
    with pytest.raises(FileExistsError):
        freeze(directory)


def test_embedding_format_changes_cache_without_changing_plain_legacy_identity(tmp_path):
    provider = SemanticProvider(SimpleNamespace(path=tmp_path / 'vectors.sqlite3'))
    profile = {'id': 'same', 'number': 1, 'config': ProfileConfig(provider='local', model='writer', embedding_model='embed-fixture').model_dump()}
    snapshot = {'writer_recall': {'semantic': {'enabled': True},
                                'sources': [{'id': 'source', 'sha256': digest('parcel'), 'text': 'parcel'}]}}
    identity = embedding_identity(profile)
    legacy = {'config': {key: value for key, value in profile['config'].items() if key != 'embedding_input_format'}, 'number': 1}
    assert identity == embedding_identity(legacy)

    def run():
        return asyncio.run(semantic_search(provider, profile, snapshot, ['obligation'], {}, lambda: None))

    assert run()['new_sources'] == 1
    assert run()['new_sources'] == 0
    profile['config']['embedding_input_format'] = 'nomic-search-v1'
    assert run()['new_sources'] == 1
    assert provider.embedding_calls[-2:] == [['search_document: parcel'], ['search_query: obligation']]
    assert run()['new_sources'] == 0
    profile['config']['embedding_input_format'] = 'plain'
    assert run()['new_sources'] == 0


def test_nomic_transport_preserves_full_maximum_chunk_and_keeps_response_limits():
    config = ProfileConfig(provider='local', model='writer', embedding_model='nomic', embedding_input_format='nomic-search-v1').model_dump()
    original = 'x' * 2400

    def handler(request):
        assert json.loads(request.content)['input'] == ['search_document: ' + original]
        return httpx.Response(200, json={'model': 'nomic', 'data': [{'index': 0, 'embedding': [1, 0]}]})

    assert asyncio.run(embed(config, None, ['search_document: ' + original], httpx.MockTransport(handler)))['model'] == 'nomic'
    with pytest.raises(DomainError, match='bounded batch'):
        asyncio.run(embed(config, None, ['search_document: ' + original + 'x'], httpx.MockTransport(handler)))
    with pytest.raises(DomainError, match='bounded batch'):
        asyncio.run(embed({**config, 'embedding_input_format': 'plain'}, None, ['search_document: ' + original], httpx.MockTransport(handler)))
