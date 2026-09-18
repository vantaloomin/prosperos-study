"""Verify withdrawal reproduces the recorded no-neighbors counterfactual.

This is a regression against an observed development result, not fresh acceptance.
"""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.memory_literature_evaluation import writer_row
from scripts.memory_literature_fixture import FIXTURES, fingerprints, literature_fixture, load_json
from server.memory.packet import ALGORITHM

FIELDS = ('fits', 'estimated_input_tokens', 'expected_groups', 'found_groups', 'any_evidence',
          'complete_evidence', 'missing_groups', 'selected', 'history_ids')


def compare(baseline):
    frozen = load_json(FIXTURES / 'freeze.json')
    key = 'tests/fixtures/long_story_literature/annotations.json'
    current = fingerprints()
    if current[key] != frozen['files'][key]:
        raise ValueError('Regression annotations changed')
    if hashlib.sha256((FIXTURES / 'freeze.json').read_bytes()).hexdigest() != baseline['freeze']['sha256']:
        raise ValueError('Baseline is not the retained freeze')
    stories, probes = literature_fixture()
    indexed = {probe['id']: probe for probe in probes}
    rows = []
    for run in baseline['writer']:
        if run['variant'] != 'no_neighbors':
            continue
        for expected in run['probes']:
            probe = indexed[expected['id']]
            actual = writer_row(stories[probe['story']], probe, 'adapted', run['context_tokens'])
            different = [field for field in FIELDS if expected[field] != actual[field]]
            rows.append({'id': probe['id'], 'context_tokens': run['context_tokens'], 'different_fields': different})
    if len(rows) != 96:
        raise ValueError('Expected all 32 queries at three context capacities')
    return {'generated_at': datetime.now(UTC).isoformat(), 'production_algorithm': ALGORITHM,
            'scope': 'Known-result regression after withdrawing automatic following passages; not a fresh quality holdout.',
            'code_fingerprints': current, 'comparisons': len(rows),
            'matching': sum(not row['different_fields'] for row in rows), 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = compare(load_json(args.baseline))
    report['baseline_sha256'] = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(f"{report['matching']}/{report['comparisons']} packets match the recorded counterfactual")
    if report['matching'] != report['comparisons']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
