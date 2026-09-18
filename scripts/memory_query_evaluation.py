"""Paired SQLite preparation timings for the latest-passage search, no inference.

Run: python -m scripts.memory_query_evaluation --repeats 20 --output planning/long-story-latest-query-performance.json
Use after other test/benchmark work has finished; do not pool this with UI TTFI.
"""
import argparse
import json
import os
import platform
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts.memory_index_evaluation import clear_process, samples_report, seed, timed_prepare
from server.main import create_app


def prepare(database, branch, variant):
    change = patch('server.memory.recall.latest_query', lambda _context: '') if variant == 'without_latest' else nullcontext()
    with change:
        return timed_prepare(database, branch)


def compare(database, branch, repeats):
    clear_process()
    first, _ = prepare(database, branch, 'adapted')
    variants = ('adapted', 'without_latest')
    primed = {variant: prepare(database, branch, variant)[1] for variant in variants}
    samples = {variant: [] for variant in variants}
    for index in range(repeats):
        order = variants if index % 2 == 0 else tuple(reversed(variants))
        for variant in order:
            elapsed, receipt = prepare(database, branch, variant)
            assert receipt == primed[variant], 'Repeated preparation changed the frozen evidence'
            samples[variant].append(elapsed)
    differences = [round(after - before, 3) for after, before in zip(samples['adapted'], samples['without_latest'], strict=True)]
    return {'path': branch['name'], 'messages': primed['adapted']['coverage']['messages'],
            'first_adapted_visit_ms': first, 'warm': {key: samples_report(values) for key, values in samples.items()},
            'paired_added_ms': samples_report(differences)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 100:
        parser.error('Use 2-100 paired samples per path.')
    with tempfile.TemporaryDirectory(prefix='prospero-query-benchmark-') as directory:
        database = create_app(Path(directory) / 'benchmark.sqlite3').state.database
        branches, counts = seed(database)
        report = {'generated_at': datetime.now(UTC).isoformat(),
                  'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                                  'processor': os.environ.get('PROCESSOR_IDENTIFIER', platform.processor()),
                                  'logical_cpus': os.cpu_count()},
                  'fixture': counts, 'canon_collections': 12, 'canon_sections_each': 80,
                  'paths': [compare(database, branch, args.repeats) for branch in branches],
                  'scope': 'Alternating warm same-fixture SQLite writer preparation with/without one query. '
                  'Initial root visit starts without a disk index; later paths share it. Repeated receipts must be stable per variant. '
                  'No provider, UI navigation/TTFI, app-startup, write transaction, concurrent load, or resource-pressure measurement.'}
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(serialized, encoding='utf-8')
        print(f'Report written to {args.output}')
    else:
        print(serialized, end='')


if __name__ == '__main__':
    main()
