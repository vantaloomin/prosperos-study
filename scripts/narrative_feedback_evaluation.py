"""Evaluate the exact production continuity-revision protocol on frozen drafts.

Feedback is supplied explicitly, as it is in the app. This measures proposed
corrections, not automatic diagnosis, and never changes accepted story data.
"""
import argparse
import asyncio
import time
from pathlib import Path

from scripts.narrative_reliability import fingerprint, load
from scripts.relationship_live_evaluation import ObservedProvider, lmstudio_config
from server.continuity_revision import PROMPT
from server.continuity_revision import freeze as request_for
from server.database import encode


def freeze(artifacts, destination):
    holdout = load(artifacts / 'narrative-review-holdout-fixture-01/manifest.json')
    checks = load(artifacts / 'narrative-review-holdout-live-01/report.json')
    earlier = load(artifacts / 'narrative-whole-revision-fixture-01/manifest.json')
    cases = []
    for case, check in zip(holdout['cases'][:12], checks['results'][:12], strict=True):
        assert check['id'] == case['id']
        concerns = [issue['explanation'] for issue in check['parsed']['issues']]
        concern = ' '.join(concerns) or 'Check whether this draft adds unsupported history or character knowledge. Change it only if needed.'
        if case['id'] == 'holdout/released_work/control':
            concern = 'Remembering the old promise seems to restore Mali’s obligation. Please check.'
        cases.append({**case, 'concern': concern})
    for case in earlier['cases']:
        if case['payload']['issues']:
            cases.append({**case, 'concern': ' '.join(issue['explanation'] for issue in case['payload']['issues'])})
    config = {'context_tokens': 10240, 'max_output_tokens': 768}
    rows = []
    for case in cases:
        payload = case['payload']
        snapshot = {'prompt': {'template': 'Write third-person fiction in the supplied scene and direction.'},
                    'content': encode(payload['context'])}
        request = request_for(snapshot, {'config': config}, {}, {'id': case['id'], 'attempt': 1, 'output': payload['draft']}, case['concern'])
        rows.append({'id': case['id'], 'request': request, 'original': payload['draft'], 'expected': case.get('expected', case.get('original_label')),
                     'review_note': case['review_note']})
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {'format': 'prospero-feedback-evaluation/1', 'protocol_prompt': PROMPT, 'config': config, 'cases': rows,
                'origin_sha256': {name: fingerprint(artifacts / name / 'manifest.json') for name in ('narrative-review-holdout-fixture-01', 'narrative-whole-revision-fixture-01')},
                'method': 'Exact production request builder; explicit feedback, fixed generic writer style instruction, full unchanged scoped source context. Six unseen flawed/control pairs plus seven development drafts with fallible concerns. One proposal each. No automatic diagnosis or acceptance. Labels withheld.'}
    (destination / 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    (destination / 'manifest.sha256').write_text(fingerprint(destination / 'manifest.json'), encoding='ascii')
    print(f'Frozen {len(rows)} production-protocol revision requests.', flush=True)


async def execute(args):
    assert fingerprint(args.fixture / 'manifest.json') == (args.fixture / 'manifest.sha256').read_text(encoding='ascii')
    manifest = load(args.fixture / 'manifest.json')
    assert manifest['protocol_prompt'] == PROMPT
    config = lmstudio_config(args.lmstudio_url, args.lmstudio_model)
    config.update(**manifest['config'], temperature=0)
    args.output.mkdir(parents=True, exist_ok=False)
    provider = ObservedProvider(None, args.output, len(manifest['cases']), config)
    report = {'format': 'prospero-feedback-evaluation-results/1', 'fixture_sha256': fingerprint(args.fixture / 'manifest.json'),
              'config': config, 'results': [], 'status': 'running'}

    def save():
        (args.output / 'report.json').write_text(encode(report), encoding='utf-8')

    started = time.perf_counter()
    try:
        for case in manifest['cases']:
            output = ''
            request = case['request']
            async for event in provider.generate({'config': config}, request['prompt'], request['content']):
                output += event.text
            report['results'].append({'id': case['id'], 'request_index': len(provider.calls) - 1,
                                      'output': output, 'changed': output != case['original'], 'review': None})
            print(case['id'], 'changed' if output != case['original'] else 'unchanged', flush=True)
            save()
        report['status'] = 'completed_unreviewed'
    except Exception as error:
        report.update(status='error', error=str(error))
        raise
    finally:
        report.update(calls=len(provider.calls), wall_seconds=time.perf_counter() - started)
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze-from', type=Path)
    mode.add_argument('--execute-live', action='store_true')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--lmstudio-model')
    parser.add_argument('--lmstudio-url', default='http://127.0.0.1:1234/v1')
    args = parser.parse_args()
    if args.freeze_from:
        freeze(args.freeze_from, args.fixture)
    elif args.output and args.lmstudio_model:
        asyncio.run(execute(args))
    else:
        parser.error('Live mode requires output and model.')
