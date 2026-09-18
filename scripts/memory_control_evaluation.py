"""Paired writer-preparation cost before/after membership-only control lookup.

Use alone, after tests finish. Two scenarios share the same disposable corpus:
no author decisions, then one exact-source decision on each measured branch.
"""
import argparse
import hashlib
import json
import os
import platform
import statistics
import tempfile
import time
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from scripts.memory_index_evaluation import body_for, clear_process, samples_report, seed
from server.database import encode
from server.generation_preparation import prepare_writer
from server.main import create_app
from server.memory.packet import ALGORITHM
from tests.test_memory_control_path import legacy_eligible_version
from tests.test_memory_controls import entry, evidence, save


def timed(database, branch, variant):
    change = patch('server.memory.control_state.eligible_version', legacy_eligible_version) if variant == 'full_path_lookup' else nullcontext()
    with change:
        started = time.perf_counter()
        with database.connect() as connection:
            prepared = prepare_writer(connection, branch['id'], body_for(branch))
        elapsed = (time.perf_counter() - started) * 1000
    # Hash outside the timed region; equality covers full inputs and author decisions.
    digest = hashlib.sha256(encode(prepared.snapshot).encode()).hexdigest()
    return round(elapsed, 3), digest, prepared.snapshot['coverage']['messages']


def measure(database, branch, repeats):
    clear_process()
    first, digest, messages = timed(database, branch, 'ids_only')
    variants = ('ids_only', 'full_path_lookup')
    for variant in variants:
        assert timed(database, branch, variant)[1] == digest, 'Priming changed exact request inputs'
    samples = {variant: [] for variant in variants}
    for index in range(repeats):
        order = variants if index % 2 == 0 else tuple(reversed(variants))
        for variant in order:
            elapsed, actual, _ = timed(database, branch, variant)
            assert actual == digest, 'Lookup optimization changed exact request inputs'
            samples[variant].append(elapsed)
    differences = [round(old - new, 3) for old, new in zip(samples['full_path_lookup'], samples['ids_only'], strict=True)]
    return {'name': branch['name'], 'messages': messages, 'snapshot_sha256': digest,
            'first_ids_only_visit_ms': first, 'warm': {key: samples_report(values) for key, values in samples.items()},
            'paired_reduction_ms': {**samples_report(differences), 'mean_ms': round(statistics.mean(differences), 3)}}


def add_decisions(database, branches):
    with TestClient(create_app(database.path), headers={'x-roleplay-client': 'workspace'}) as client:
        for branch in branches:
            source = evidence(client, branch['id'])[0]
            save(client, branch['id'], [entry([source], 'emphasis', 'motif', subject='A remembered detail')])


def evaluate(repeats):
    with tempfile.TemporaryDirectory(prefix='prospero-control-benchmark-') as directory:
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
    return {'generated_at': datetime.now(UTC).isoformat(), 'production_algorithm': ALGORITHM,
            'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                            'processor': os.environ.get('PROCESSOR_IDENTIFIER', platform.processor()), 'logical_cpus': os.cpu_count()},
            'fixture': counts, 'canon_collections': 12, 'canon_sections_each': 80,
            'repeats_per_variant_per_path': repeats, 'scenarios': scenarios,
            'scope': 'Paired alternating warm SQLite writer preparation with identical exact snapshots. '
            'Both methods use the retired-neighbor-free selection policy. First root visit starts without a disk index; '
            'later paths/scenarios share it. This is not navigation/TTFI, inference, concurrent/resource-pressure '
            'testing, fresh-process cold startup, or a statistical significance claim.'}


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
