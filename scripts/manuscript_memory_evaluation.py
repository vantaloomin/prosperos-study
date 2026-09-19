"""Measure real-prose retrieval, frozen-archive size and optional live semantics.

Uses locally preserved public-domain works and pre-existing evidence labels.
The collection-length case measures scale only; it is not one coherent novel.
No writer inference or model-authored annotations are used in this benchmark.
"""
import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

from scripts.memory_literature_evaluation import context_for
from scripts.memory_literature_fixture import FIXTURES, literature_fixture, source_texts
from scripts.memory_literature_metrics import evidence_coverage
from scripts.memory_quality_metrics import exact_ranges
from server.database import encode
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.hybrid_recall import hybrid_hits
from server.memory.index import index_session
from server.memory.packet import assemble_memory
from server.memory.retrieval import term_counts, terms
from server.memory.semantic_recall import semantic_search
from server.memory.writer_recall import freeze_sources
from server.memory.writer_recall_packet import pack_recall, search_sources
from server.prompts import DEFAULT_WRITER
from server.providers.config import ProfileConfig
from server.providers.service import ProviderService
from server.providers.vault import SystemVault


def measured_sources():
    stories, probes = literature_fixture()
    text = source_texts()['pg1661.txt']
    start = text.index('\n', text.index('*** START OF')) + 1
    text = text[start:text.index('*** END OF', start)]
    chunks = compile_chunks('collection', '', text)
    stories['collection_scale_only'] = {'title': 'Holmes collection (scale only)', 'text': text,
        'sources': [{'id': f'collection:{index:04d}', 'text': chunk.text} for index, chunk in enumerate(chunks)]}
    return stories, probes


def freeze(destination):
    stories, probes = measured_sources()
    data = {'format': 'prospero-manuscript-evidence/1', 'stories': stories, 'probes': probes,
            'prompt': DEFAULT_WRITER, 'budgets': [4096, 8192],
            'annotation_sha256': hashlib.sha256((FIXTURES / 'annotations.json').read_bytes()).hexdigest(),
            'method': 'Existing labels, no score-driven edits. Whole-work author view. Unknown queries have no scored answer evidence. Collection case measures storage/time only.'}
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'manifest.json').write_text(encode(data), encoding='utf-8')
    digest = hashlib.sha256((destination / 'manifest.json').read_bytes()).hexdigest()
    (destination / 'manifest.sha256').write_text(digest, encoding='ascii')
    print(f'Frozen {len(stories)} source corpora and {len(probes)} probes. No inference.', flush=True)


def snapshot_for(context, profile, prompt):
    packet, memory = assemble_memory(context, prompt, [profile])
    return {'content': encode(packet), 'prompt': {'template': prompt}, 'memory': memory,
            'coverage': memory['coverage'], 'estimated_input_tokens': token_estimate(prompt, packet),
            'writer_recall': freeze_sources(context)}


def build_context(story, probe):
    context = context_for(story, probe)
    context['story']['settings'].update(experience='directed', player_agency='shared')
    context['story']['settings']['memory'].update(writer_recall=True, semantic_recall=True)
    return context


def measured_snapshot(context, profile, prompt, path):
    started = time.perf_counter()
    with index_session(path):
        snapshot = snapshot_for(context, profile, prompt)
    return snapshot, time.perf_counter() - started


def clear_process_caches():
    for function in (compile_chunks, term_counts, terms):
        function.cache_clear()


def scale_rows(manifest, directory):
    rows = []
    for key, story in manifest['stories'].items():
        for budget in manifest['budgets']:
            context = build_context(story, {'query': 'Continue consistently with earlier commitments and their outcomes.'})
            profile = {'config': {'context_tokens': budget, 'max_output_tokens': 512}}
            path = directory / f'{key}-{budget}.memory.sqlite3'
            clear_process_caches()
            first, initial = measured_snapshot(context, profile, manifest['prompt'], path)
            clear_process_caches()
            _, disk_warm = measured_snapshot(context, profile, manifest['prompt'], path)
            _, warm = measured_snapshot(context, profile, manifest['prompt'], path)
            rows.append({'corpus': key, 'words': len(story['text'].split()), 'characters': len(story['text']),
                         'sources': len(first['writer_recall']['sources']), 'context_tokens': budget,
                         'first_seconds': initial, 'disk_warm_seconds': disk_warm,
                         'warm_seconds': warm, 'cache_bytes': path.stat().st_size,
                         'snapshot_bytes': len(encode(first).encode('utf-8')),
                         'archive_bytes': len(encode(first['writer_recall']).encode('utf-8')),
                         'final_input_bytes': len(first['content'].encode('utf-8')),
                         'estimated_input_tokens': first['estimated_input_tokens'],
                         'fits': first['estimated_input_tokens'] + first['memory']['overhead_margin'] <= budget - 512})
            print(f'{key} {budget}: source/archive sizes and preparation measured', flush=True)
    return rows


class ObservedEmbeddings:
    def __init__(self, directory, name):
        self.database = SimpleNamespace(path=directory / (name + '.sqlite3'))
        self.service = ProviderService(SystemVault())
        self.calls = []

    async def embed(self, profile, texts):
        start = time.perf_counter()
        call = {'inputs': len(texts), 'input_sha256': hashlib.sha256(encode(texts).encode()).hexdigest(), 'status': 'running'}
        self.calls.append(call)
        try:
            result = await self.service.embed(profile, texts)
            call.update(status='done', model=result['model'], usage=result['usage'])
            return result
        except Exception as error:
            call.update(status='error', error=str(error))
            raise
        finally:
            call['seconds'] = time.perf_counter() - start
            self.database.path.with_suffix('.requests.json').write_text(encode(self.calls), encoding='utf-8')


def ranking_coverage(probe, ids, sources):
    by_id = {row['id']: row for row in sources}
    ranges = [{**by_id[identity], 'source_id': by_id[identity]['source_id'].removeprefix('message:')} for identity in ids]
    return evidence_coverage(probe, ranges)


def packet_row(probe, snapshot, queries, semantic, originals):
    result = pack_recall(snapshot, queries, semantic)
    final = result['final_input']
    packet = json.loads(final['content'])
    return {**evidence_coverage(probe, exact_ranges(packet, originals)),
            'estimated_input_tokens': final['estimated_input_tokens'],
            'fits': final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= final['memory']['input_allowance']}


async def probe_rows(manifest, directory, config):
    rows, warming, providers = [], [], {}
    for probe in manifest['probes']:
        story = manifest['stories'][probe['story']]
        context = build_context(story, probe)
        profile = {'id': 'evaluation-fixed-profile', 'number': 1, 'config': config}
        snapshot = snapshot_for(context, profile, manifest['prompt'])
        sources = snapshot['writer_recall']['sources']
        originals = {row['id']: row['text'] for row in story['sources']}
        queries = [probe['query']]
        lexical = search_sources(sources, queries)
        row = {'probe': probe['id'], 'story': probe['story'], 'lexical_top8': ranking_coverage(probe, [h.chunk.id for h in lexical], sources),
               'lexical_packet': packet_row(probe, snapshot, queries, None, originals)}
        if config.get('embedding_model'):
            provider = providers.setdefault(probe['story'], ObservedEmbeddings(directory, probe['story']))
            semantic = await semantic_search(provider, profile, snapshot, queries, {}, lambda: None)
            warming.append({'probe': probe['id'], **semantic})
            row.update(semantic_status=semantic['status'], semantic_calls=semantic['calls'])
            if semantic['status'] == 'completed':
                row.update(semantic_top8=ranking_coverage(probe, [h['id'] for h in semantic['rankings'][0]], sources),
                           fusion_top8=ranking_coverage(probe, [h.chunk.id for h in hybrid_hits(sources, queries, semantic)], sources),
                           fusion_packet=packet_row(probe, snapshot, queries, semantic, originals))
        rows.append(row)
        print(probe['id'] + ': evidence measured', flush=True)
    return rows, warming, {key: value.calls for key, value in providers.items()}


async def collection_warming(manifest, directory, config):
    context = build_context(manifest['stories']['collection_scale_only'], {'query': 'A broken promise and its consequences.'})
    profile = {'id': 'scale-fixed-profile', 'number': 1, 'config': config}
    snapshot = snapshot_for(context, profile, manifest['prompt'])
    provider = ObservedEmbeddings(directory, 'collection-warming')
    receipts = []
    for _ in range(8):
        report = await semantic_search(provider, profile, snapshot, [context['direction']], {}, lambda: None)
        receipts.append(report)
        if report['status'] == 'completed':
            receipts.append(await semantic_search(provider, profile, snapshot, [context['direction']], {}, lambda: None))
            break
        if report.get('new_sources', 0) == 0:
            break
    cache = directory / '.cache' / 'collection-warming.sqlite3.memory.sqlite3'
    return {'receipts': receipts, 'calls': provider.calls, 'cache_bytes': cache.stat().st_size if cache.exists() else 0,
            'method': 'Explicitly repeated bounded semantic preparations, then one warm query. No writer calls; no narrative-quality claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute-live-embeddings', action='store_true')
    parser.add_argument('--embedding-model', default='')
    parser.add_argument('--embedding-input-format', choices=['plain', 'nomic-search-v1'], default='plain')
    args = parser.parse_args()
    if args.freeze:
        freeze(args.fixture)
        return
    if not args.output or bool(args.embedding_model) != args.execute_live_embeddings:
        parser.error('Use a new --output; live embeddings require both --execute-live-embeddings and --embedding-model.')
    data = (args.fixture / 'manifest.json').read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == (args.fixture / 'manifest.sha256').read_text(encoding='ascii')
    manifest = json.loads(data)
    args.output.mkdir(parents=True, exist_ok=False)
    config = ProfileConfig(provider='local', model='unused-writer', embedding_model=args.embedding_model,
                           embedding_input_format=args.embedding_input_format,
                           context_tokens=8192, max_output_tokens=512).model_dump()
    report = {'fixture_sha256': digest, 'config': config, 'scale': scale_rows(manifest, args.output),
              'scale_method': 'Clear chunk/term/count process caches before empty-disk measurement, clear again for disk-warm, then measure process-warm. Same process, filesystem cache uncontrolled; not process-start latency.'}
    (args.output / 'report.json').write_text(encode(report), encoding='utf-8')
    rows, warming, calls = asyncio.run(probe_rows(manifest, args.output, config))
    report.update(probes=rows, semantic_receipts=warming, embedding_calls=calls)
    if args.execute_live_embeddings:
        report['collection_warming'] = asyncio.run(collection_warming(manifest, args.output, config))
    (args.output / 'report.json').write_text(encode(report), encoding='utf-8')


if __name__ == '__main__':
    main()
