import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from server.memory.cache import ByteCache
from server.memory.chunks import compile_chunks
from server.memory.index import index_session
from server.memory.retrieval import Corpus, term_counts, terms


def clear_process_indexes():
    for function in (compile_chunks, terms, term_counts):
        function.cache_clear()


def indexed_passage():
    chunks = compile_chunks('message:accepted', 'Earlier event', 'Mara hid the orchid medallion beneath the piano.')
    return Corpus(chunks).search('orchid medallion')


def test_persistent_index_reuses_exact_chunks_and_counts_after_process_cache_reset(tmp_path):
    path = tmp_path / 'index.sqlite3'
    clear_process_indexes()
    with index_session(path) as index:
        expected = indexed_passage()
    assert index.writes == 2
    clear_process_indexes()
    with index_session(path) as restarted:
        actual = indexed_passage()
    assert restarted.hits == 2 and restarted.writes == 0
    assert actual == expected


def test_corrupted_or_misbound_index_rows_are_rebuilt_from_sources(tmp_path):
    path = tmp_path / 'index.sqlite3'
    clear_process_indexes()
    with index_session(path):
        expected = indexed_passage()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE entries SET payload=?,digest=?", (b'[]', hashlib.sha256(b'[]').hexdigest()))
    clear_process_indexes()
    with index_session(path) as repaired:
        assert indexed_passage() == expected
    assert repaired.misses == repaired.writes == 2
    clear_process_indexes()
    with index_session(path) as clean:
        assert indexed_passage() == expected
    assert clean.hits == 2


def test_process_cache_evicts_by_retained_bytes_and_skips_oversized_values():
    cache = ByteCache(2048)
    cache.put('recent', ('x' * 500,))
    assert cache.get('recent') is not None
    for index in range(8):
        cache.put(str(index), ('word' * 125 + str(index),))
        assert cache.info()['bytes'] <= 2048
    assert cache.get('recent') is None and cache.get('7') is not None
    cache.put('huge', ('x' * 10000,))
    assert cache.get('huge') is None and cache.info()['bytes'] <= 2048


def test_disk_pressure_evicts_derived_entries_with_a_fixed_payload_budget(tmp_path):
    path = tmp_path / 'index.sqlite3'
    with index_session(path, limit=16 * 1024) as index:
        for number in range(250):
            key = hashlib.sha256(str(number).encode()).hexdigest()
            index.put(key, ('derived reference ' * 30).encode())
    with sqlite3.connect(path) as connection:
        count, size = connection.execute('SELECT COUNT(*),SUM(size) FROM entries').fetchone()
    assert 0 < count < 250 and size <= 16 * 1024
    assert path.stat().st_size <= 16 * 1024 + 4 * 1024 * 1024


def test_unavailable_or_locked_cache_never_blocks_exact_source_retrieval(tmp_path):
    blocked = tmp_path / 'a-file'
    blocked.write_text('Unrelated user file', encoding='utf-8')
    clear_process_indexes()
    with index_session(blocked / 'index.sqlite3') as unavailable:
        assert unavailable is None
        assert indexed_passage()[0].chunk.source_id == 'message:accepted'
    path = tmp_path / 'locked.sqlite3'
    with index_session(path):
        pass
    with sqlite3.connect(path, isolation_level=None) as locked:
        locked.execute('BEGIN EXCLUSIVE')
        clear_process_indexes()
        with index_session(path):
            assert indexed_passage()[0].chunk.source_id == 'message:accepted'
        locked.rollback()
    assert blocked.read_text(encoding='utf-8') == 'Unrelated user file'


def test_shared_index_never_adds_sibling_words_to_eligible_corpus_statistics(tmp_path):
    path = tmp_path / 'index.sqlite3'
    with index_session(path):
        foreign = compile_chunks('message:sibling', 'Abandoned future', 'The orchid medallion belongs to the murderer.')
        Corpus(foreign).search('murderer')
    clear_process_indexes()
    with index_session(path):
        allowed = compile_chunks('message:accepted', 'Earlier event', 'The orchid medallion was hidden.')
        corpus = Corpus(allowed)
        assert 'murderer' not in corpus.df
        assert corpus.search('murderer') == []
        assert {hit.chunk.source_id for hit in corpus.search('orchid medallion')} == {'message:accepted'}


def test_unicode_terms_and_alias_revisions_have_separate_content_keys(tmp_path):
    clear_process_indexes()
    assert terms("Ivo\u2019s caf\u00e9") == terms("Ivo's caf\u00e9")
    with index_session(tmp_path / 'index.sqlite3'):
        first = compile_chunks('version:one', 'Garden', 'An orchid.', aliases=('silver blossom',))
        second = compile_chunks('version:one', 'Garden', 'An orchid.', aliases=('black petal',))
        assert Corpus(first).search('silver blossom')
        assert not Corpus(second).search('silver blossom')


def test_concurrent_index_sessions_return_identical_sources(tmp_path):
    path = tmp_path / 'index.sqlite3'
    with index_session(path):
        pass
    clear_process_indexes()

    def retrieve(_number):
        with index_session(path):
            return indexed_passage()

    with ThreadPoolExecutor(max_workers=4) as executor:
        outputs = list(executor.map(retrieve, range(12)))
    assert all(output == outputs[0] for output in outputs)


def test_invalid_json_cache_is_discarded_without_interpreting_objects(tmp_path):
    path = tmp_path / 'index.sqlite3'
    clear_process_indexes()
    with index_session(path):
        expected = indexed_passage()
    with sqlite3.connect(path) as connection:
        for (key,) in connection.execute('SELECT key FROM entries').fetchall():
            payload = b'{"unexpected":"shape"}'
            connection.execute('UPDATE entries SET payload=?,digest=? WHERE key=?',
                               (payload, hashlib.sha256(key.encode() + payload).hexdigest(), key))
    clear_process_indexes()
    with index_session(path):
        assert indexed_passage() == expected
