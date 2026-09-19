"""Freeze paired evidence-use trials separately from executing any live requests.

Uses identical source context for both variants; the candidate adds only the
predeclared instruction. Raw prior artifacts remain untouched. No app profiles
or accepted stories are modified. This isolates writer behavior, not retrieval.
"""
import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from scripts.narrative_reliability_contract import CASE_NOTES, EVIDENCE_GUIDANCE, RUBRIC
from scripts.relationship_live_evaluation import ObservedProvider, lmstudio_config
from server.database import encode
from server.memory.budget import token_estimate


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def freeze(previous, destination):
    report = load(previous / 'report.json')
    requests = load(previous / 'requests.json')
    rows = []
    for case in report['cases']:
        variant = next(row for row in case['variants'] if row['variant'] == 'prewriting_and_links')
        content = variant['final_content']
        call = next(row for row in requests if row['kind'] == 'writer' and row['content'] == content)
        rows.append({'case': case['case'], 'content': content, 'baseline_prompt': call['prompt'],
                     'candidate_prompt': call['prompt'] + '\n\n' + EVIDENCE_GUIDANCE,
                     'review_note': CASE_NOTES[case['case']],
                     'evidence': {key: variant[key] for key in ('required_passages', 'covered_passages', 'missing',
                                                               'forbidden_passages_supplied')}})
    data = {'format': 'prospero-narrative-paired/1', 'rubric': RUBRIC, 'cases': rows,
            'context_tokens': 4608, 'max_output_tokens': 512, 'overhead_margin': 128, 'temperature': 0.4,
            'origin': {name: fingerprint(previous / name) for name in ('report.json', 'requests.json')},
            'method': 'Fixed identical linked evidence; alternating order; nonblind qualitative review. No gold notes enter model input.'}
    for row in rows:
        for prompt in ('baseline_prompt', 'candidate_prompt'):
            assert token_estimate(row[prompt], load_content(row)) + data['overhead_margin'] <= 4096
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'manifest.json').write_text(encode(data), encoding='utf-8')
    (destination / 'manifest.sha256').write_text(fingerprint(destination / 'manifest.json'), encoding='ascii')
    print(f'Frozen {len(rows)} paired cases; no provider requests.', flush=True)


def load_content(row):
    return json.loads(row['content'])


async def execute(args):
    assert fingerprint(args.fixture / 'manifest.json') == (args.fixture / 'manifest.sha256').read_text(encoding='ascii')
    manifest = load(args.fixture / 'manifest.json')
    config = lmstudio_config(args.lmstudio_url, args.lmstudio_model)
    config.update(context_tokens=manifest['context_tokens'], max_output_tokens=manifest['max_output_tokens'],
                  temperature=manifest['temperature'])
    rows = [row for row in manifest['cases'] if not args.cases or row['case'] in args.cases]
    assert rows and 1 <= args.repetitions <= 5
    args.output.mkdir(parents=True, exist_ok=False)
    provider = ObservedProvider(None, args.output, len(rows) * 2 * args.repetitions, config)
    result = {'format': 'prospero-narrative-paired-results/1', 'fixture_sha256': fingerprint(args.fixture / 'manifest.json'),
              'config': config, 'repetitions': args.repetitions, 'results': [], 'status': 'running'}
    started = time.perf_counter()
    try:
        for repetition in range(args.repetitions):
            for row in rows:
                order = ('baseline', 'candidate') if repetition % 2 == 0 else ('candidate', 'baseline')
                for variant in order:
                    output = ''
                    async for event in provider.generate({'config': config}, row[variant + '_prompt'], row['content']):
                        output += event.text
                    result['results'].append({'case': row['case'], 'repetition': repetition + 1, 'variant': variant,
                                              'output': output, 'request_index': len(provider.calls) - 1,
                                              'narrative_review': None})
                    (args.output / 'report.json').write_text(encode(result), encoding='utf-8')
                    print(f"{row['case']} repeat {repetition + 1} {variant}: saved", flush=True)
                if (args.output / 'stop-after-pair').exists():
                    result['status'] = 'stopped_between_pairs'
                    return
        result['status'] = 'completed_unreviewed'
    except Exception as error:
        result.update(status='error', error=str(error))
        raise
    finally:
        result.update(calls=len(provider.calls), wall_seconds=time.perf_counter() - started)
        (args.output / 'report.json').write_text(encode(result), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze-from', type=Path)
    mode.add_argument('--execute-live', action='store_true')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--lmstudio-model')
    parser.add_argument('--lmstudio-url', default='http://127.0.0.1:1234/v1')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--cases', nargs='+', choices=CASE_NOTES)
    args = parser.parse_args()
    if args.freeze_from:
        freeze(args.freeze_from, args.fixture)
    elif not args.output or not args.lmstudio_model:
        parser.error('Live mode needs --output and --lmstudio-model.')
    else:
        asyncio.run(execute(args))


if __name__ == '__main__':
    main()
