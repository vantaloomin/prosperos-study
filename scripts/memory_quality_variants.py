"""Benchmark-only alternatives; production routing/settings are never changed.

Run sequentially: temporary function patches isolate exactly one retrieval
choice per run. The adapted variant calls the unchanged production assembler.
"""
import math
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

from scripts.memory_scoring import RawProductCorpus
from server.memory.budget import token_estimate
from server.memory.packet import add_recent, assemble_memory, minimum_context
from server.memory.retrieval import Corpus, Hit

VARIANTS = {
    'adapted': 'Production layered assembler, reviewed aids and active threads.',
    'full_history': 'All eligible prose, only when the same input allowance fits.',
    'recent_only': 'Required material plus as much contiguous recent prose as fits; no older search.',
    'bm25': 'Same layers and budgets; history scoring uses pure normalized BM25.',
    'cosine': 'Same layers and budgets; history scoring uses pure TF-IDF cosine.',
    'raw_product': 'Same layers and budgets; history score is TF-IDF cosine times raw BM25.',
    'no_summaries': 'Remove reviewed summaries/topics, retaining reviewed aliases.',
    'no_aliases': 'Remove reviewed aliases, retaining reviewed summaries/topics.',
    'no_reviewed_aids': 'Remove all reviewed summary/topic/alias search cues.',
    'no_neighbors': 'Legacy ablation: current production already omits automatic following passages.',
    'no_latest_query': 'Remove the latest-passage query; retain the previous combined recent query.',
    'no_recent_query': 'Do not add recent prose to the search query; keep the recent context layer.',
    'no_threads': 'Disable open-thread source search; accepted continuity itself stays required.',
}


class BM25Corpus(Corpus):
    def score(self, index, query, query_norm, cosine_only=False):
        frequency = self.frequencies[index]
        matched = tuple(sorted(query.keys() & frequency.keys()))
        raw = sum(self.bm25(term, frequency[term], self.lengths[index]) for term in matched)
        scale = math.log(1 + (len(self.chunks) - 0.5) / 1.5) if self.chunks else 1
        return Hit(self.chunks[index], 1 - math.exp(-raw / max(scale, 1)), matched)


class CosineCorpus(Corpus):
    def search(self, query, limit=16, threshold=0.01, *, cosine_only=False):
        return super().search(query, limit, threshold, cosine_only=True)


def adapt_aids(aids, variant):
    if variant == 'no_reviewed_aids':
        return {}
    result = deepcopy(aids)
    for aid in result.values():
        if variant == 'no_summaries':
            aid.update(summary='', topics=[])
        if variant == 'no_aliases':
            aid['aliases'] = []
    return result


def recent_packet(context, prompt, profile):
    allowance = profile['config']['context_tokens'] - profile['config']['max_output_tokens']
    margin = min(512, max(128, allowance // 50))
    packet, included = minimum_context(context)
    add_recent(context, packet, included, prompt, allowance - margin)
    return packet, {'input_allowance': allowance, 'overhead_margin': margin, 'selected': []}


def assemble_variant(context, prompt, profile, aids, variant):
    if variant not in VARIANTS:
        raise ValueError(f'Unknown evaluation variant: {variant}')
    context = deepcopy(context)
    settings = context['story']['settings']['memory']
    if variant == 'full_history':
        settings['mode'] = 'full'
    if variant == 'no_threads':
        settings['open_threads'] = False
    if variant == 'recent_only':
        return recent_packet(context, prompt, profile)
    with ExitStack() as stack:
        scorer = {'bm25': BM25Corpus, 'cosine': CosineCorpus, 'raw_product': RawProductCorpus}.get(variant)
        if scorer:
            stack.enter_context(patch('server.memory.recall.Corpus', scorer))
        if variant == 'no_recent_query':
            stack.enter_context(patch('server.memory.recall.current_query', lambda value: value['direction']))
            stack.enter_context(patch('server.memory.recall.latest_query', lambda value: value['direction']))
        if variant == 'no_latest_query':
            stack.enter_context(patch('server.memory.recall.latest_query', lambda value: ''))
        if variant == 'no_neighbors':
            stack.enter_context(patch('server.memory.recall.with_following_context', lambda hits, *_args: hits, create=True))
        return assemble_memory(context, prompt, [profile], summary_aids=adapt_aids(aids, variant))


def packet_budget(packet, receipt, prompt, profile):
    allowance = profile['config']['context_tokens'] - profile['config']['max_output_tokens']
    margin = (receipt or {}).get('overhead_margin', min(512, max(128, allowance // 50)))
    estimated = token_estimate(prompt, packet)
    return {'estimated_input_tokens': estimated, 'input_allowance': allowance,
            'overhead_margin': margin, 'fits': estimated + margin <= allowance}
