"""Replay frozen live semantic rankings through old/new packing, without inference."""
import argparse
import json
from copy import deepcopy
from pathlib import Path

from scripts.manuscript_memory_evaluation import build_context, snapshot_for
from scripts.memory_literature_metrics import aggregate, evidence_coverage
from scripts.memory_quality_metrics import exact_ranges
from scripts.narrative_reliability import fingerprint, load
from server.database import encode
from server.memory.writer_recall_packet import pack_recall


def evaluate(fixture, semantic_report, destination):
    assert fingerprint(fixture / 'manifest.json') == (fixture / 'manifest.sha256').read_text(encoding='ascii')
    manifest, previous = load(fixture / 'manifest.json'), load(semantic_report)
    assert previous['fixture_sha256'] == fingerprint(fixture / 'manifest.json')
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for probe, semantic, recorded in zip(manifest['probes'], previous['semantic_receipts'], previous['probes'], strict=True):
        assert probe['id'] == semantic['probe'] == recorded['probe']
        story = manifest['stories'][probe['story']]
        snapshot = snapshot_for(build_context(story, probe), {'config': previous['config']}, manifest['prompt'])
        originals = {source['id']: source['text'] for source in story['sources']}
        for mode in ('lexical', 'fusion'):
            for version in (4, 5):
                trial = deepcopy(snapshot)
                trial['writer_recall']['version'] = version
                result = pack_recall(trial, [probe['query']], semantic if mode == 'fusion' else None)
                final = result['final_input']
                metrics = {**evidence_coverage(probe, exact_ranges(json.loads(final['content']), originals)),
                           'estimated_input_tokens': final['estimated_input_tokens'],
                           'fits': final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= final['memory']['input_allowance']}
                if version == 4:
                    assert metrics == recorded[mode + '_packet'], 'Legacy replay changed.'
                assert metrics['fits'] and result['evidence_tokens'] <= result['evidence_allowance']
                rows.append({'probe': probe['id'], 'mode': mode, 'version': version, **metrics, 'receipt': result})
    report = {'method': 'Same frozen labels, context, queries, semantic rankings and allowances. No inference or gold-guided selection.',
              'fixture_sha256': fingerprint(fixture / 'manifest.json'), 'semantic_report_sha256': fingerprint(semantic_report),
              'results': rows, 'aggregate': {f'{mode}-v{version}': aggregate([row for row in rows if row['mode'] == mode and row['version'] == version])
                                           for mode in ('lexical', 'fusion') for version in (4, 5)}}
    (destination / 'report.json').write_text(encode(report), encoding='utf-8')
    print(json.dumps(report['aggregate'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--semantic-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.fixture, args.semantic_report, args.output)
