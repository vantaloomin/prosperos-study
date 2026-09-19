from threading import Event

import pytest

from server.branches import insert_node
from server.database import Database, one
from server.memory.chunks import compile_chunks
from server.memory.index import connection_index
from server.memory.preparation_runner import MAX_PENDING, MAX_TEXT, PreparationRunner, warm_node
from server.memory.retrieval import Corpus, term_counts
from server.providers.scheduling import RequestScheduler


def test_warming_reuses_exact_existing_index_and_preserves_retrieval(tmp_path):
    database = Database(tmp_path / 'preparation.sqlite3')
    node = {'id': 'passage', 'role': 'assistant', 'text': 'Mara hid the orchid medallion beneath the piano.'}
    compile_chunks.cache_clear()
    term_counts.cache_clear()
    assert warm_node(database, node, Event()) == 1
    compile_chunks.cache_clear()
    term_counts.cache_clear()
    with database.connect() as connection, connection_index(connection) as index:
        chunks = compile_chunks('message:passage', 'assistant passage', node['text'])
        hits = Corpus(chunks).search('orchid medallion')
        assert index.hits == 2 and index.misses == 0
        assert hits[0].chunk.text == node['text']
        assert Corpus([]).search('orchid medallion') == []
    changed = {**node, 'text': 'Mara left the medallion in the tower.'}
    warm_node(database, changed, Event())
    chunks = compile_chunks('message:passage', 'assistant passage', changed['text'])
    assert chunks[0].text == changed['text']


def test_preparation_is_bounded_and_interruptible(tmp_path):
    database = Database(tmp_path / 'bounds.sqlite3')
    runner = PreparationRunner(database, RequestScheduler())
    runner.enqueue([{'id': str(index), 'role': 'assistant', 'text': 'A passage.'} for index in range(MAX_PENDING + 5)])
    assert len(runner.pending) == MAX_PENDING and runner.stats['coalesced'] == 5
    runner.enqueue([{'id': str(MAX_PENDING), 'role': 'assistant', 'text': 'Updated.'}])
    assert len(runner.pending) == MAX_PENDING
    stop = Event()
    stop.set()
    assert warm_node(database, {'id': 'stopped', 'role': 'assistant', 'text': 'A passage.'}, stop) == 0
    assert warm_node(database, {'id': 'large', 'role': 'assistant', 'text': 'x' * (MAX_TEXT + 1)}, Event()) == 0


def test_only_committed_nodes_notify_and_cache_failure_cannot_fail_write(client, story):
    database = client.app.state.database
    notifications = []
    database.node_listeners.append(notifications.extend)
    with pytest.raises(RuntimeError):
        with database.connect(write=True) as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
            insert_node(connection, branch, 'Rolled back text.', 'assistant', {})
            raise RuntimeError('rollback')
    assert notifications == []
    database.node_listeners.append(lambda _: (_ for _ in ()).throw(RuntimeError('cache unavailable')))
    with database.connect(write=True) as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        node_id = insert_node(connection, branch, 'Committed text.', 'assistant', {})
    assert notifications[0]['id'] == node_id
    with database.connect() as connection:
        assert one(connection, 'SELECT text FROM nodes WHERE id=?', (node_id,))['text'] == 'Committed text.'
