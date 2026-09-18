"""Development/regression comparison of memory assembly and declared ablations.

Run: python -m scripts.memory_ablation --output planning/long-story-memory-ablation.json
No server, provider, user database or external source is used. Output contains
all per-probe misses as well as grouped metrics; no answer is scored by an LLM.
"""
import argparse
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.memory_quality_metrics import expected_ranges, grouped, measure_evidence, summarize
from scripts.memory_quality_variants import VARIANTS, assemble_variant, packet_budget
from server.memory.chunks import compile_chunks
from server.memory.packet import ALGORITHM
from tests.memory_challenge_fixture import evaluation_probes, evaluation_sources

PROMPT = ('Continue the accepted story using the supplied evidence. Preserve uncertainty, '
          'chronology and character knowledge; missing evidence is unknown.')
OUTPUT_RESERVE = 512


def reviewed_aids(sources):
    aids = {}
    for source in sources:
        if not source.get('summary') and not source.get('aliases'):
            continue
        for chunk in compile_chunks(f"message:{source['id']}", 'narrator passage', source['text']):
            aids[chunk.id] = {'source_sha256': chunk.digest, 'version_id': f"reviewed:{source['id']}",
                             'summary': source.get('summary', ''), 'topics': [],
                             'aliases': source.get('aliases', [])}
    return aids


def probe_context(sources, probe):
    head = 'They arrived at the quiet meeting place and waited for someone to speak.'
    entries = []
    if 'recent_query' in probe['features']:
        head = 'The verdigris talisman was on the table. They examined it.'
    if 'thread_only' in probe['features']:
        entries = [{'kind': 'thread', 'status': 'active', 'subject': 'Neris and Esra’s orchard promise',
                    'text': 'Neris pledged a living seed from the sealed orchard.'}]
    history = [{'id': source['id'], 'text': source['text'], 'role': 'narrator', 'metadata': {}}
               for source in sources]
    history.append({'id': 'evaluation-head', 'text': head, 'role': 'narrator', 'metadata': {}})
    return {'story': {'title': 'Authored retrieval evaluation', 'premise': '',
                      'settings': {'memory': {'mode': 'long', 'summary_recall': True, 'recall_limit': 8}}},
            'history': history, 'direction': probe['query'], 'library': [], 'continuity': {'entries': entries}}


def fixture():
    sources, probes = evaluation_sources(), evaluation_probes()
    originals = {source['id']: source['text'] for source in sources}
    if len(originals) != len(sources) or len({row['id'] for row in probes}) != len(probes):
        raise ValueError('Duplicate evaluation identities')
    for probe in probes:
        expected_ranges(probe, originals)
    payload = json.dumps({'sources': sources, 'probes': probes}, sort_keys=True, ensure_ascii=False)
    return sources, probes, hashlib.sha256(payload.encode()).hexdigest()


def evaluate_probe(sources, probe, aids, variant, context_tokens):
    context = probe_context(sources, probe)
    originals = {node['id']: node['text'] for node in context['history']}
    profile = {'config': {'context_tokens': context_tokens, 'max_output_tokens': OUTPUT_RESERVE}}
    packet, receipt = assemble_variant(context, PROMPT, profile, aids, variant)
    budget = packet_budget(packet, receipt, PROMPT, profile)
    evidence = measure_evidence(packet, receipt, probe, originals, budget['fits'])
    return {'id': probe['id'], 'genres': [probe['genre']], 'features': probe['features'],
            'origin': probe['origin'], **budget, **evidence}


def quality_comparison(budgets=(4096, 8192, 65536), variants=tuple(VARIANTS), *, progress=False):
    sources, probes, fingerprint = fixture()
    aids = reviewed_aids(sources)
    runs = []
    for context_tokens in budgets:
        for variant in variants:
            rows = [evaluate_probe(sources, probe, aids, variant, context_tokens) for probe in probes]
            runs.append({'context_tokens': context_tokens, 'variant': variant, 'overall': summarize(rows),
                         'by_genre': grouped(rows, 'genres'), 'by_feature': grouped(rows, 'features'),
                         'by_origin': {origin: summarize([row for row in rows if row['origin'] == origin])
                                       for origin in ('original', 'challenge')}, 'probes': rows})
            if progress:
                print(f'{context_tokens}: {variant} finished ({len(rows)} probes)', file=sys.stderr, flush=True)
    return {'format': 'prospero-retrieval-ablation/1', 'fixture_sha256': fingerprint,
            'generated_at': datetime.now(UTC).isoformat(),
            'environment': {'python': platform.python_version(), 'platform': platform.platform()},
            'production_algorithm': ALGORITHM, 'variants': {key: VARIANTS[key] for key in variants},
            'fixture': {'sources': len(sources), 'source_utf8_bytes': sum(len(row['text'].encode()) for row in sources),
                        'probes': len(probes), 'answerable': sum(bool(row['expected']) for row in probes),
                        'reviewed_aid_chunks': len(aids)},
            'contract': contract(), 'runs': runs}


def contract():
    return {
        'cost': 'UTF-8 serialized-input bytes / 3 rounded up; estimates, not provider token counts. Output reserve 512.',
        'budget': 'Every variant uses the same declared context and overhead margin. Oversized Full history is blocked, not silently truncated.',
        'evidence': 'Gold exact ranges, not just source IDs. Complete evidence requires every gold range; adjacent selected ranges may jointly cover a quote.',
        'precision': 'Mean per-answerable-probe fraction of optional recalled chunks overlapping a gold range. Recent/required prose excluded; probes with no optional chunks excluded.',
        'unanswerable': 'Related passages can be retrieved without answering the question. Nonempty optional evidence is not itself an invented answer.',
        'ablations': 'BM25/cosine change history scoring only. No recent query removes query expansion, not recent context. No threads removes thread retrieval, not continuity.',
        'scope': 'In-process author-view assembler with already eligible accepted sources and reviewed aids. Existing API tests, not this harness, establish branch/version/privacy permissions.',
        'limits': 'Synthetic development suite used to guide implementation; not an independent quality holdout. No real-manuscript generalization, semantic entailment, provider quality, Canon-ranking evaluation, navigation timing or resource benchmark.',
        'fairness': 'Labels are separate from retrieval inputs, but prior suite failures guided code changes. All variants receive the same source order, query, exact originals and budget. Per-probe active-thread/recent-query cues are explicit fixture inputs. No tuning or ground-truth oracle is supplied to the assembler.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context-tokens', nargs='+', type=int, default=[4096, 8192, 65536])
    parser.add_argument('--variants', nargs='+', choices=tuple(VARIANTS), default=list(VARIANTS))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not all(2048 <= value <= 1048576 for value in args.context_tokens):
        parser.error('Use context capacities between 2048 and 1048576.')
    report = quality_comparison(tuple(dict.fromkeys(args.context_tokens)), tuple(dict.fromkeys(args.variants)), progress=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(serialized, encoding='utf-8')
        print(f'Report written to {args.output}')
    else:
        print(serialized, end='')


if __name__ == '__main__':
    main()
