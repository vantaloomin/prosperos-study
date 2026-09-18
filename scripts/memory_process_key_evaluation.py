"""Paired warm writer preparation with old JSON keys versus immutable text keys.

Run alone, after tests. Full snapshots must match, not just retrieved source IDs.
The old method is the exact prior key serialization on every process lookup.
"""
import argparse
import hashlib
import json
import os
import platform
import statistics
import tempfile
import time
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts.memory_control_evaluation import add_decisions
from scripts.memory_index_evaluation import body_for, clear_process, samples_report, seed
from server.database import encode
from server.generation_preparation import prepare_writer
from server.main import create_app
from server.memory.cache import ByteCache, disk_key
from server.memory.chunks import compile_chunks
from server.memory.packet import ALGORITHM
from server.memory.retrieval import term_counts, terms

VARIANTS = ('immutable_text_key', 'previous_json_key')


@contextmanager
def process_pool(pool):
    # Benchmark-only state isolation. Each variant keeps the same production byte
    # caps; variants must not evict one another merely by alternating samples.
    owners = [(function.cache_info.__self__, pool[function.__name__])
              for function in (compile_chunks, terms, term_counts)]
    for owner, other in owners:
        swap_cache_state(owner, other)
    try:
        yield
    finally:
        for owner, other in reversed(owners):
            swap_cache_state(owner, other)


def swap_cache_state(owner, other):
    with owner.lock:
        for field in ('values', 'bytes', 'hits', 'misses'):
            original = getattr(owner, field)
            setattr(owner, field, getattr(other, field))
            setattr(other, field, original)


def timed(database, branch, variant, pool):
    change = patch('server.memory.cache.process_key', disk_key) if variant == 'previous_json_key' else nullcontext()
    with change, process_pool(pool):
        started = time.perf_counter()
        with database.connect() as connection:
            prepared = prepare_writer(connection, branch['id'], body_for(branch))
        elapsed = (time.perf_counter() - started) * 1000
    # Deliberately excluded from the timing interval.
    digest = hashlib.sha256(encode(prepared.snapshot).encode()).hexdigest()
    return round(elapsed, 3), digest, prepared.snapshot['coverage']['messages']


def cache_pool():
    return {function.__name__: ByteCache(function.cache_info()['limit'])
            for function in (compile_chunks, terms, term_counts)}


def measure(database, branch, repeats):
    clear_process()
    pools = {variant: cache_pool() for variant in VARIANTS}
    first, digest, messages = timed(database, branch, VARIANTS[0], pools[VARIANTS[0]])
    for variant in VARIANTS:
        assert timed(database, branch, variant, pools[variant])[1] == digest, 'Priming changed prepared inputs'
    samples = {variant: [] for variant in VARIANTS}
    for index in range(repeats):
        order = VARIANTS if index % 2 == 0 else tuple(reversed(VARIANTS))
        for variant in order:
            elapsed, actual, _ = timed(database, branch, variant, pools[variant])
            assert actual == digest, 'Cache-key variant changed exact prepared inputs'
            samples[variant].append(elapsed)
    differences = [round(old - new, 3) for old, new in zip(samples[VARIANTS[1]], samples[VARIANTS[0]], strict=True)]
    usage = {variant: {name: cache.info() for name, cache in pool.items()} for variant, pool in pools.items()}
    assert all(item['bytes'] <= item['limit'] for pool in usage.values() for item in pool.values())
    return {'name': branch['name'], 'messages': messages, 'snapshot_sha256': digest,
            'first_new_key_visit_ms': first, 'warm': {key: samples_report(values) for key, values in samples.items()},
            'paired_reduction_ms': {**samples_report(differences), 'mean_ms': round(statistics.mean(differences), 3)},
            'separate_process_caches': usage}


def evaluate(repeats):
    with tempfile.TemporaryDirectory(prefix='prospero-process-key-benchmark-') as directory:
        database = create_app(Path(directory) / 'benchmark.sqlite3').state.database
        branches, counts = seed(database)
        scenarios = []
        for state in ('no_author_decisions', 'with_author_decisions'):
            if state == 'with_author_decisions':
                add_decisions(database, branches)
            paths = []
            for branch in branches:
                paths.append(measure(database, branch, repeats))
                print(f"{state}: {branch['name']} finished", flush=True)
            scenarios.append({'state': state, 'paths': paths})
    files = ('server/memory/cache.py', 'server/memory/retrieval.py', 'server/memory/packet.py',
             'scripts/memory_process_key_evaluation.py', 'scripts/memory_index_evaluation.py')
    return {'generated_at': datetime.now(UTC).isoformat(), 'production_algorithm': ALGORITHM,
            'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                            'processor': os.environ.get('PROCESSOR_IDENTIFIER', platform.processor()), 'logical_cpus': os.cpu_count()},
            'code_sha256': {file: hashlib.sha256(Path(file).read_bytes()).hexdigest() for file in files},
            'fixture': counts, 'canon_collections': 12, 'canon_sections_each': 80,
            'repeats_per_variant_per_path': repeats, 'scenarios': scenarios,
            'scope': 'Alternating paired warm SQLite writer preparation. Both variants share identical sources, '
            'eligible corpus, scoring, byte limits and disk format. Each variant has a separate process cache '
            'with the same production byte caps; both pools reside in the benchmark process. First root '
            'visit has no disk index; later paths and scenarios share it. Not navigation/TTFI, inference, '
            'concurrent/resource-pressure, fresh-process '
            'cold startup, whole-process RAM measurement or statistical significance evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 100 or args.output.exists():
        parser.error('Use 2-100 samples and a new output path.')
    report = evaluate(args.repeats)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(f'Report written to {args.output}')


if __name__ == '__main__':
    main()
