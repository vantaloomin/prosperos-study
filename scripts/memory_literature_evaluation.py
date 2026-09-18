"""Frozen TF-IDF / BM25 / product comparison and separate writer assembly evaluation.

Prepare once with --freeze; run with --output PATH. No provider or app server.
"""
import argparse
import json
import platform
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from scripts.memory_ablation import OUTPUT_RESERVE, PROMPT
from scripts.memory_literature_fixture import freeze_fixture, literature_fixture, verify_freeze
from scripts.memory_literature_metrics import aggregate, evidence_coverage
from scripts.memory_quality_metrics import exact_ranges
from scripts.memory_quality_variants import assemble_variant, packet_budget
from scripts.memory_scoring import SCORERS
from server.memory.chunks import compile_chunks
from server.memory.packet import ALGORITHM

BUDGETS = (4096, 8192, 65536)
LAYERED = ('adapted', 'cosine', 'bm25', 'raw_product', 'no_neighbors', 'recent_only', 'full_history')


def context_for(story, probe):
    return {'story': {'title': 'Manuscript evidence evaluation', 'premise': '',
                      'settings': {'memory': {'mode': 'long', 'recall_limit': 8, 'summary_recall': False}}},
            'history': [{'id': row['id'], 'role': 'narrator', 'text': row['text'], 'metadata': {}}
                        for row in story['sources']],
            'direction': probe['query'], 'library': [], 'continuity': {'entries': []}}


def profile_for(budget):
    return {'config': {'context_tokens': budget, 'max_output_tokens': OUTPUT_RESERVE}}


def identity(probe):
    return {key: probe[key] for key in ('id', 'story', 'query', 'features', 'rationale')}


def grouped_result(rows):
    stories = sorted({row['story'] for row in rows})
    features = sorted({feature for row in rows for feature in row['features']})
    return {'overall': aggregate(rows),
            'by_story': {story: aggregate([r for r in rows if r['story'] == story]) for story in stories},
            'by_feature': {feature: aggregate([r for r in rows if feature in r['features']]) for feature in features},
            'probes': rows}


def scorer_corpora(stories):
    result = {}
    for key, story in stories.items():
        chunks = [chunk for source in story['sources']
                  for chunk in compile_chunks(f"message:{source['id']}", '', source['text'])]
        result[key] = {name: scorer(chunks) for name, scorer in SCORERS.items()}
    return result


def ranked_packet(context, hits, budget, *, enforce_budget):
    packet = {**deepcopy(context), 'history': [], 'recalled_passages': []}
    selected = []
    for hit in hits:
        packet['recalled_passages'].append(hit.chunk.evidence())
        cost = packet_budget(packet, None, PROMPT, profile_for(budget))
        if enforce_budget and not cost['fits']:
            packet['recalled_passages'].pop()
            break  # Prefix policy is fixed for all scorers; no gold-guided packing.
        selected.append({'id': hit.chunk.id, 'score': hit.score, 'matched_terms': list(hit.matched)})
    return packet, selected


def ranking_row(story, probe, corpus, selection, budget):
    context = context_for(story, probe)
    hits = [hit for hit in corpus.search(probe['query'], len(corpus.chunks), threshold=0) if hit.score > 0]
    chosen = hits[:int(selection.removeprefix('top_'))] if selection.startswith('top_') else hits
    packet, selected = ranked_packet(context, chosen, budget, enforce_budget=selection == 'budget')
    originals = {row['id']: row['text'] for row in story['sources']}
    ranges = exact_ranges(packet, originals)
    cost = packet_budget(packet, None, PROMPT, profile_for(budget))
    return {**identity(probe), **cost, **evidence_coverage(probe, ranges),
            'positive_score_candidates': len(hits), 'selected': selected}


def ranking_runs(stories, probes, *, progress):
    corpora = scorer_corpora(stories)
    runs = []
    selections = [('top_1', 65536), ('top_3', 65536), ('top_8', 65536),
                  *(('budget', budget) for budget in BUDGETS)]
    for scorer in SCORERS:
        for selection, budget in selections:
            rows = [ranking_row(stories[p['story']], p, corpora[p['story']][scorer], selection, budget) for p in probes]
            runs.append({'scorer': scorer, 'selection': selection, 'context_tokens': budget,
                         **grouped_result(rows)})
        if progress:
            print(f'Isolated scoring: {scorer} finished', file=sys.stderr, flush=True)
    return runs


def writer_row(story, probe, variant, budget):
    packet, receipt = assemble_variant(context_for(story, probe), PROMPT, profile_for(budget), {}, variant)
    cost = packet_budget(packet, receipt, PROMPT, profile_for(budget))
    originals = {row['id']: row['text'] for row in story['sources']}
    ranges = exact_ranges(packet, originals) if cost['fits'] else []
    return {**identity(probe), **cost, **evidence_coverage(probe, ranges),
            'selected': (receipt or {}).get('selected', []),
            'history_ids': [node['id'] for node in packet['history']] if cost['fits'] else []}


def writer_runs(stories, probes, *, progress):
    runs = []
    for budget in BUDGETS:
        for variant in LAYERED:
            rows = [writer_row(stories[p['story']], p, variant, budget) for p in probes]
            runs.append({'variant': variant, 'context_tokens': budget, **grouped_result(rows)})
        if progress:
            print(f'Writer assembly: context {budget} finished', file=sys.stderr, flush=True)
    return runs


def contract():
    return {
        'scorers': 'Identical tokenizer, stoplist, chunks, query and corpus-local statistics. No labels, aliases or summaries supplied. TF-IDF means cosine with raw TF and smoothed IDF; BM25 k1=1.2, b=0.75.',
        'products': 'raw_product = TF-IDF cosine * raw BM25. bounded_product = cosine * (1-exp(-BM25/scale)); scale=max(log(1+(N-.5)/1.5),1). Production already uses the bounded product.',
        'isolated': 'Direction-only search; positive scores only, deterministic ties. No query expansion, recent prose, threads, following passages or minimum score .01. top_K is uncapped ranking; budget runs take a ranked prefix fitting the common allowance.',
        'writer': 'Separate unchanged production assembly plus one-scorer counterfactuals. Same budgets and .01 history threshold; this threshold is not scale-calibrated across methods. Normalized BM25 and raw BM25 have identical standalone rankings, but different admission scores.',
        'budget': 'Context minus 512 output reserve and production overhead margin. UTF-8 serialized bytes / 3 estimate, not provider tokens. Oversized Full history is blocked, never counted as delivered evidence.',
        'labels': '24 answerable questions with required evidence groups and declared alternatives; eight unknowns. Assistant-authored before scored retrieval, not human-adjudicated. Exact-span coverage is evidence availability, not answer correctness.',
        'precision': 'Fraction of selected ranges overlapping annotated gold ranges; other passages may also be useful or sufficient. In writer runs this includes recent history; do not compare directly with older optional-only precision.',
        'unknown': 'Selecting related text is not answering. No abstention pass rate or hallucination claim is inferred from retrieval alone.',
        'limits': 'Four English public-domain stories, simulated message boundaries, whole-story author view. No real user manuscript, character permission, historical cutoff, cross-branch, generated prose, latency or statistical superiority claim.',
        'policy': 'Freeze predates the first scored run. No scorer tuning or query/label adjustment to chase scores; retain failures for subsequent independently reviewed evaluation.',
    }


def evaluate(*, progress=False):
    frozen = verify_freeze()
    stories, probes = literature_fixture()
    return {'format': 'prospero-literature-evaluation/1', 'freeze': frozen,
            'generated_at': datetime.now(UTC).isoformat(), 'production_algorithm': ALGORITHM,
            'environment': {'python': platform.python_version(), 'platform': platform.platform()},
            'fixture': {key: {'title': s['title'], 'characters': len(s['text']), 'sources': len(s['sources'])}
                        for key, s in stories.items()}, 'contract': contract(),
            'ranking': ranking_runs(stories, probes, progress=progress),
            'writer': writer_runs(stories, probes, progress=progress)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.freeze:
        if args.output:
            parser.error('--freeze is separate from evaluation; omit --output.')
        result = freeze_fixture()
        print(f"Frozen {len(result['files'])} input/code fingerprints. No retrieval run.")
        return
    if not args.output:
        parser.error('Supply a new --output file; existing evidence is never overwritten.')
    if args.output.exists():
        parser.error('Output already exists; retain it and choose a different path.')
    report = evaluate(progress=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(f'Report written to {args.output}')


if __name__ == '__main__':
    main()
