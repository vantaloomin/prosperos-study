"""Fast process lookups must preserve the existing persistent identity and scope."""
import hashlib
import json
from unittest.mock import patch

import pytest

from scripts.memory_process_key_evaluation import cache_pool, process_pool
from server.memory.cache import disk_key, memoized, process_key
from server.memory.chunks import compile_chunks
from server.memory.index import index_session
from server.memory.retrieval import Corpus, term_counts, terms
from tests.test_memory_index import clear_process_indexes, indexed_passage


def test_warm_text_lookups_skip_json_and_hashing_without_changing_outputs():
    clear_process_indexes()
    args = ('message:accepted', '雨 🔑', 'The café door may open.', 'narrator', ('lunar doorway',))
    expected = compile_chunks(*args)
    expected_terms, expected_counts = terms(args[2]), term_counts(args[2])
    with patch('server.memory.cache.disk_key', side_effect=AssertionError('Warm lookup serialized text')):
        assert compile_chunks(*args) == expected
        assert terms(args[2]) == expected_terms
        assert term_counts(args[2]) == expected_counts


def test_disk_keys_keep_exact_old_namespace_argument_and_keyword_serialization():
    args, kwargs = ('雨 🔑', 'line one\r\nline two', ('one', 'two')), {'kind': 'narration'}
    old = hashlib.sha256(json.dumps(['old-v1', args, kwargs], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert disk_key('old-v1', args, kwargs) == old
    assert process_key('old-v1', args, kwargs) != old
    assert process_key('old-v1', (['mutable'],), {}) == disk_key('old-v1', (['mutable'],), {})


def test_existing_disk_index_loads_without_recomputing_sources_after_key_change(tmp_path):
    clear_process_indexes()
    with patch('server.memory.cache.process_key', disk_key), index_session(tmp_path / 'index.sqlite3') as old:
        expected = indexed_passage()
    assert old.writes == 2
    clear_process_indexes()
    with index_session(tmp_path / 'index.sqlite3') as current:
        assert indexed_passage() == expected
    assert current.hits == 2 and current.writes == 0


def test_mutated_alias_lists_recompute_and_never_borrow_sibling_statistics():
    clear_process_indexes()
    aliases = ['silver blossom']
    first = compile_chunks('node:sibling', 'Garden', 'An orchid.', aliases=aliases)
    aliases[0] = 'black petal'
    revised = compile_chunks('node:sibling', 'Garden', 'An orchid.', aliases=aliases)
    accepted = compile_chunks('node:accepted', 'Garden', 'An orchid.')
    assert first != revised
    assert Corpus(first).search('silver blossom')
    assert not Corpus(revised).search('silver blossom')
    assert not Corpus(accepted).search('black petal')


def test_retained_argument_bytes_are_charged_and_oversized_keys_are_not_cached():
    calls = []

    @memoized('small-value-large-key', 2048)
    def small_result(text):
        calls.append(len(text))
        return ('constant',)

    for _ in range(2):
        assert small_result('雨' * 10000) == ('constant',)
    assert calls == [10000, 10000] and small_result.cache_info()['entries'] == 0
    for index in range(20):
        small_result('a' * 400 + str(index))
        assert small_result.cache_info()['bytes'] <= 2048


def test_falsey_results_and_keyword_source_identity_remain_distinct():
    calls = []

    @memoized('empty-values', 4096)
    def empty(text, **kwargs):
        calls.append((text, kwargs))
        return ()

    empty('same', kind='one')
    empty('same', kind='two')
    empty('same', kind='one')
    assert len(calls) == 2 and empty.cache_info()['hits'] == 1


@pytest.mark.parametrize('interrupted', [False, True])
def test_benchmark_variants_preserve_separate_cache_state_even_after_failure(interrupted):
    clear_process_indexes()
    pools = [cache_pool(), cache_pool()]
    terms('production cache')
    original = terms.cache_info()
    try:
        with process_pool(pools[0]):
            terms('first variant')
            assert terms.cache_info()['entries'] == 1
            if interrupted:
                raise RuntimeError('interrupted sample')
    except RuntimeError:
        assert interrupted
    assert terms.cache_info() == original
    with process_pool(pools[1]):
        assert terms.cache_info()['entries'] == 0
        terms('second variant')
        terms('another second variant')
    with process_pool(pools[0]):
        assert terms.cache_info()['entries'] == 1
        terms('first variant')
        assert terms.cache_info()['hits'] == 1
    assert terms.cache_info() == original
    assert pools[1]['terms'].info()['entries'] == 2
    assert all(cache.info()['bytes'] <= cache.info()['limit'] for pool in pools for cache in pool.values())
    clear_process_indexes()
