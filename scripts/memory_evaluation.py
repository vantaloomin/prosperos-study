"""Reproducible local retrieval evaluation; no app server or provider calls.

Run: python -m scripts.memory_evaluation --repeats 20
Timings cover the in-process packet assembler, not database loading or navigation.
"""
import argparse
import json
import math
import os
import platform
import statistics
import time
from collections import defaultdict

from server.character_content import narrative_asset
from server.memory.chunks import compile_chunks
from server.memory.packet import assemble_memory
from server.memory.retrieval import Corpus, term_counts, terms
from tests.memory_quality_fixture import passages, probes


def quality_report():
    sources = passages()
    corpus = Corpus(chunk for source in sources
                    for chunk in compile_chunks(source['id'], '', source['text']))
    genres = defaultdict(lambda: {'answerable': 0, 'hits_at_8': 0, 'absent': 0, 'absent_with_hits': 0})
    failures, precisions = [], []
    for probe in probes():
        returned = list(dict.fromkeys(hit.chunk.source_id for hit in corpus.search(probe['query'], limit=8)))
        expected = set(probe['expected'])
        result = genres[probe['genre']]
        if expected:
            result['answerable'] += 1
            result['hits_at_8'] += int(bool(expected.intersection(returned)))
            precisions.append(len(expected.intersection(returned)) / max(len(returned), 1))
            if not expected.intersection(returned):
                failures.append({'id': probe['id'], 'expected': probe['expected'], 'returned': returned})
        else:
            result['absent'] += 1
            result['absent_with_hits'] += int(bool(returned))
    recent_ids = {source['id'] for source in sources[-8:]}
    return {'probes': len(probes()), 'authored_sources': 48, 'distractors': len(sources) - 48,
            'genres': dict(genres), 'misses': failures,
            'mean_expected_source_precision_at_8': round(statistics.mean(precisions), 4),
            'recent_only_last_8_hits': sum(bool(set(probe['expected']) & recent_ids) for probe in probes()),
            'limitations': 'Lexical fixture with explicit evidence; no semantic paraphrase, provider-writing '
            'or production-corpus quality claim. Exact source precision counts only the authored answer source.'}


def benchmark_context(count, variable=False):
    sources = passages()[:48]
    history = []
    for index in range(count - 1):
        source = sources[index % len(sources)]
        repeats = (1, 5, 12, 30, 2)[index % 5] if variable else 12
        history.append({'id': f'bench-{index}', 'role': 'narrator',
                        'text': source['text'] * repeats + f' Record {index}.', 'metadata': {}})
    history.append({'id': 'head', 'role': 'narrator', 'text': 'Éléonore returned to the piano.', 'metadata': {}})
    return {'story': {'title': 'Memory benchmark', 'premise': '', 'settings': {'memory': {'mode': 'long'}}},
            'history': history, 'direction': 'Recall the orchid medallion and the piano stool.',
            'library': [], 'continuity': {'entries': []}}



def benchmark_canon(collections, sections):
    sources = passages()[:48]
    assets = []
    for collection in range(collections):
        text = ''.join(f'## Reference {index}\n\n' + sources[(index + collection) % len(sources)]['text'] * 8 + '\n\n'
                       for index in range(sections))
        version = {'id': f'canon-version-{collection}', 'asset_id': f'canon-{collection}',
                   'number': 1, 'name': f'Canon {collection}',
                   'content': {'text': text, 'canon_recall': {'mode': 'relevant'}}}
        assets.append({'version_id': version['id'], 'asset_id': version['asset_id'], 'version': version,
                       'enabled': True, 'kind': 'lorebook', 'priority': 0})
    return assets


def measure(count, repeats, variable=False, canon_collections=0, canon_sections=80):
    context = benchmark_context(count, variable)
    assets = benchmark_canon(canon_collections, canon_sections)
    context['library'] = [narrative_asset(item) for item in assets]
    profiles = [{'config': {'context_tokens': 8192, 'max_output_tokens': 512}}]
    compile_chunks.cache_clear()
    terms.cache_clear()
    term_counts.cache_clear()
    timings = []
    for _ in range(repeats + 1):
        start = time.perf_counter()
        _, receipt = assemble_memory(context, 'Continue the accepted story.', profiles, canon_assets=assets)
        timings.append(round((time.perf_counter() - start) * 1000, 3))
    warm = timings[1:]
    return {'messages': count, 'canon_collections': canon_collections, 'canon_sections_per_collection': canon_sections,
            'canon_source_bytes': sum(len(item['version']['content']['text'].encode()) for item in assets), 'lengths': 'mixed' if variable else 'similar',
            'source_bytes': sum(len(node['text'].encode()) for node in context['history']),
            'cold_ms': timings[0], 'warm_samples_ms': warm,
            'warm_p95_ms': sorted(warm)[math.ceil(len(warm) * 0.95) - 1], 'warm_max_ms': max(warm),
            'coverage': receipt['coverage']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--canon-collections', type=int, default=0)
    parser.add_argument('--canon-sections', type=int, default=80)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error('Use 1–100 warm samples.')
    if not 0 <= args.canon_collections <= 100 or not 1 <= args.canon_sections <= 1000:
        parser.error('Use 0-100 Canon collections and 1-1000 sections per collection.')
    result = {'environment': {'platform': platform.platform(), 'python': platform.python_version(),
              'processor': os.environ.get('PROCESSOR_IDENTIFIER', platform.processor()), 'logical_cpus': os.cpu_count()},
              'quality': quality_report(), 'performance': [measure(count, args.repeats, variable, args.canon_collections, args.canon_sections)
              for count, variable in ((100, False), (1000, False), (3000, False), (3000, True))],
              'performance_scope': 'In-process synthetic assembler only; Canon sizes listed per workload. No SQLite '
              'loading, branch navigation, providers, summaries, concurrency or resource-pressure test.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
