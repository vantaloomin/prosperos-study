"""SQLite-backed, branching Long story preparation/index benchmark; no inference.

Run: python -m scripts.memory_index_evaluation --repeats 20
Includes an empty index, process-cache resets, shared ancestors, differing path
lengths, deep nested forks, and recording time under the author-database write lock.
"""
import argparse
import json
import math
import platform
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from scripts.memory_evaluation import benchmark_canon, benchmark_context, quality_report
from server.assessment.writing import WritingRequests
from server.database import now
from server.generation_models import GenerateRequest
from server.generation_preparation import prepare_writer
from server.main import create_app
from server.memory.chunks import compile_chunks
from server.memory.retrieval import term_counts, terms
from tests.test_memory import small_profile


def seed_path(connection, story, parent, count, prefix, *, mixed=True):
    history = benchmark_context(count, mixed)['history']
    rows = []
    for index, item in enumerate(history):
        node_id = f'{prefix}-{index}'
        rows.append((node_id, story['story_id'], parent, item['role'], item['text'], story['manifest_id'], '{}', now()))
        parent = node_id
    connection.executemany('INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)', rows)
    return parent


def seed_branch(connection, story, name, parent_branch, fork_node, count, prefix):
    head = seed_path(connection, story, fork_node, count, prefix)
    branch_id = uuid4().hex
    connection.execute('INSERT INTO branches VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (branch_id, story['story_id'], name, head, story['manifest_id'], parent_branch, fork_node, 0, now(), now()))
    return {'id': branch_id, 'head': head, 'revision': 0, 'name': name}


def seed(database):
    with TestClient(create_app(database.path), headers={'x-roleplay-client': 'workspace'}) as client:
        small_profile(client, limit=8192)
        attachments = []
        for asset in benchmark_canon(12, 80):
            version = asset['version']
            response = client.post('/api/library', json={'kind': 'lorebook', 'name': version['name'], 'content': version['content']})
            response.raise_for_status()
            saved = response.json()
            attachments.append({'asset_id': saved['asset_id'], 'version_id': saved['id']})
        story = client.post('/api/stories', json={'title': 'Indexed branch benchmark', 'attachments': attachments,
                                               'settings': {'memory': {'mode': 'long'}}}).json()
        detail = client.get(f"/api/stories/{story['story_id']}").json()
        story['manifest_id'] = detail['manifest_id']
    with database.connect(write=True) as connection:
        head = seed_path(connection, story, None, 3000, 'root')
        connection.execute('UPDATE branches SET head_id=?,revision=? WHERE id=?', (head, 3000, story['branch_id']))
        root = {'id': story['branch_id'], 'head': head, 'revision': 3000, 'name': '3,000-message root'}
        short = seed_branch(connection, story, 'Short fork', root['id'], 'root-19', 12, 'short')
        child = seed_branch(connection, story, 'Uneven child', root['id'], 'root-1499', 130, 'child')
        deep = child
        for index in range(250):
            deep = seed_branch(connection, story, f'Nested fork {index}', deep['id'], deep['head'],
                               (1, 3, 7, 2, 12)[index % 5], f'deep-{index}')
        for index in range(64):
            seed_branch(connection, story, f'Wide sibling {index}', root['id'], f'root-{index * 31}',
                        1 + index % 23, f'wide-{index}')
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('nodes', 'branches', 'asset_versions')}
    return [root, short, child, {**deep, 'name': '250 nested sub-branches'}], counts


def clear_process():
    for function in (compile_chunks, terms, term_counts):
        function.cache_clear()


def body_for(branch):
    return GenerateRequest(operation_id=uuid4().hex, expected_revision=branch['revision'], assess_beat=False,
                           direction='Recall the orchid medallion and the piano stool.')


def timed_prepare(database, branch):
    started = time.perf_counter()
    with database.connect() as connection:
        prepared = prepare_writer(connection, branch['id'], body_for(branch))
    elapsed = (time.perf_counter() - started) * 1000
    return round(elapsed, 3), prepared.snapshot['memory']


def samples_report(samples):
    return {'samples_ms': samples, 'p95_ms': sorted(samples)[math.ceil(len(samples) * .95) - 1], 'maximum_ms': max(samples)}


def measure(database, branch, repeats):
    clear_process()
    first, receipt = timed_prepare(database, branch)
    clear_process()
    restarted, restored_receipt = timed_prepare(database, branch)
    assert restored_receipt == receipt, 'Index reload changed the frozen memory receipt'
    warm = []
    for _ in range(repeats):
        elapsed, current = timed_prepare(database, branch)
        assert current == receipt, 'Warm cache changed recall'
        warm.append(elapsed)
    return {'name': branch['name'], 'messages': receipt['coverage']['messages'],
            'first_visit_ms': first, 'process_cache_reset_ms': restarted, 'warm': samples_report(warm)}


def write_lock_report(database, branch, repeats):
    original = database.connect
    held = []

    @contextmanager
    def timed_connection(write=False):
        with original(write) as connection:
            started = time.perf_counter()
            yield connection
        if write:
            held.append(round((time.perf_counter() - started) * 1000, 3))

    database.connect = timed_connection
    total = []
    try:
        for _ in range(repeats):
            started = time.perf_counter()
            WritingRequests(database).create(branch['id'], body_for(branch))
            total.append(round((time.perf_counter() - started) * 1000, 3))
    finally:
        database.connect = original
    return {'total_request': samples_report(total), 'write_transaction': samples_report(held)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error('Use 1-100 warm samples.')
    with tempfile.TemporaryDirectory(prefix='prospero-index-benchmark-') as directory:
        app = create_app(Path(directory) / 'benchmark.sqlite3')
        database = app.state.database
        branches, counts = seed(database)
        result = {'environment': {'platform': platform.platform(), 'python': platform.python_version()},
                  'fixture': counts, 'canon_collections': 12, 'canon_sections_each': 80,
                  'quality': quality_report(), 'paths': [measure(database, branch, args.repeats) for branch in branches],
                  'recording': write_lock_report(database, branches[0], args.repeats),
                  'process_caches': {function.__name__: function.cache_info() for function in (compile_chunks, terms, term_counts)},
                  'index_file_bytes': (database.path.parent / '.cache' / (database.path.name + '.memory.sqlite3')).stat().st_size,
                  'scope': 'Synthetic SQLite-backed preparation plus separate queued-request recording. First root visit starts '
                  'with no disk index; later paths share indexed ancestors. Process-cache resets retain OS/file caches. '
                  'No app-startup, UI navigation/TTFI, inference, concurrent load or whole-process memory claim.'}
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
