"""Compare explicit thinking off/on on identical frozen evidence and prompt.

This is a local model-setting experiment, not a production setting change.
Both variants have the same enlarged output reserve so reasoning cost is visible.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from scripts.narrative_reliability import fingerprint, load
from scripts.relationship_live_evaluation import ObservedProvider, lmstudio_config
from server.database import encode
from server.memory.budget import token_estimate

CASES = {'successful_sibling', 'excluded_handoff', 'fork_before_handoff', 'unwitnessed_warehouse'}


def freeze(fixtures, destination):
    rows = []
    for fixture in fixtures:
        assert fingerprint(fixture / 'manifest.json') == (fixture / 'manifest.sha256').read_text(encoding='ascii')
        for row in load(fixture / 'manifest.json')['cases']:
            if row['case'] in CASES:
                assert token_estimate(row['baseline_prompt'], json.loads(row['content'])) + 128 <= 6144 - 1536
                rows.append({**row, 'origin_sha256': fingerprint(fixture / 'manifest.json')})
    assert {row['case'] for row in rows} == CASES and len(rows) == 4
    manifest = {'format': 'prospero-reasoning-contrast/1', 'cases': rows, 'context_tokens': 6144,
                'max_output_tokens': 1536, 'temperature': 0.4, 'repetitions': 2,
                'method': 'Same baseline prompt and source bytes; thinking off versus on, twice in opposite orders. Labels withheld; no extra reading or checker stage. No claims about another model.'}
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    (destination / 'manifest.sha256').write_text(fingerprint(destination / 'manifest.json'), encoding='ascii')
    print('Frozen four off/on pairs, two repetitions; no inference.', flush=True)


async def execute(args):
    assert fingerprint(args.fixture / 'manifest.json') == (args.fixture / 'manifest.sha256').read_text(encoding='ascii')
    manifest = load(args.fixture / 'manifest.json')
    base = lmstudio_config(args.lmstudio_url, args.lmstudio_model)
    base.update(context_tokens=manifest['context_tokens'], max_output_tokens=manifest['max_output_tokens'], temperature=manifest['temperature'])
    args.output.mkdir(parents=True, exist_ok=False)
    providers = {}
    for mode in ('off', 'on'):
        path = args.output / mode
        path.mkdir()
        providers[mode] = ObservedProvider(None, path, 8, {**base, 'local_reasoning': mode})
    report = {'format': 'prospero-reasoning-contrast-results/1', 'fixture_sha256': fingerprint(args.fixture / 'manifest.json'),
              'config': base, 'results': [], 'status': 'running'}

    def save():
        (args.output / 'report.json').write_text(encode(report), encoding='utf-8')

    started = time.perf_counter()
    try:
        for row in manifest['cases']:
            for repetition in (1, 2):
                for mode in (('off', 'on') if repetition == 1 else ('on', 'off')):
                    provider = providers[mode]
                    output = ''
                    async for event in provider.generate({'config': provider.config}, row['baseline_prompt'], row['content']):
                        output += event.text
                    report['results'].append({'case': row['case'], 'repetition': repetition, 'thinking': mode,
                                              'output': output, 'request_index': len(provider.calls) - 1, 'review': None})
                    save()
                    print(f"{row['case']} repeat {repetition} thinking {mode}: saved", flush=True)
        report['status'] = 'completed_unreviewed'
    except Exception as error:
        report.update(status='error', error=str(error))
        raise
    finally:
        report.update(calls=sum(len(provider.calls) for provider in providers.values()), wall_seconds=time.perf_counter() - started)
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze-from', type=Path, nargs='+')
    mode.add_argument('--execute-live', action='store_true')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--lmstudio-model')
    parser.add_argument('--lmstudio-url', default='http://127.0.0.1:1234/v1')
    args = parser.parse_args()
    if args.freeze_from:
        freeze(args.freeze_from, args.fixture)
    elif not args.output or not args.lmstudio_model:
        parser.error('Live mode requires --output and --lmstudio-model.')
    else:
        asyncio.run(execute(args))
