"""Exact-source memory for scene work and privileged reviews, after role scoping."""
import hashlib

from server.database import decode, encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.control_packet import excluded_chunks, excluded_nodes
from server.memory.neighbors import anchor_present, neighbor_receipt
from server.memory.recall import with_aid
from server.memory.retrieval import Corpus
from server.memory.scoped_aids import chunk_key, source_aid
from server.memory.settings import memory_settings
from server.memory.source_evidence import cited_ids
from server.memory.summary_excerpt import smaller_summary, summary_excerpt

GUIDANCE = (
    'Some earlier accepted prose is omitted. These are exact source excerpts, not summaries. '
    'Review targets, author guidance, selected references and proposed working material are '
    'preserved. A proposed scene is not accepted history. Missing context is unknown, not '
    'evidence of a contradiction. Cite only the supplied source IDs and exact text.'
)
SUMMARY_GUIDANCE = (
    'Some earlier prose is omitted. Reviewed summaries are explicitly labeled interpretations, '
    'with exact grounding quotes and source coordinates; they are not exact transcripts. '
    'Keep uncertainty, character knowledge and unresolved accounts distinct. Missing detail '
    'does not establish a contradiction. Required working material remains exact.'
)
HISTORY_KINDS = {'previous', 'accepted'}


def eligible(source):
    return source['kind'] in HISTORY_KINDS and source['title'] != 'ooc contribution'


def required_positions(sources):
    history = [index for index, source in enumerate(sources) if eligible(source)]
    required = {index for index, source in enumerate(sources) if not eligible(source)}
    return required | set(history[-1:]), history


def required_context(context):
    required, history = required_positions(context['sources'])
    cited = cited_ids(context)
    required.update(index for index, source in enumerate(context['sources']) if source['id'] in cited)
    return required, history


def whole(index, reason):
    return {'index': index, 'reason': reason}


def source_excerpt(source, selection):
    if 'start' not in selection:
        return source
    start, end = selection['start'], selection['end']
    if selection.get('reviewed_summary'):
        return summary_excerpt(source['id'], start, end, selection['sha256'], selection['reviewed_aid'])
    text = source['text'][start:end]
    digest = hashlib.sha256(text.encode()).hexdigest()
    relation = {'recall_relation': selection['reason']} if 'adjacent_to' in selection else {}
    return {**source, 'id': f"{source['id']}@{start}:{end}:{digest[:12]}",
            'source_id': source['id'], 'text': text, 'start': start, 'end': end, 'sha256': digest, **relation}


def ordered(selection):
    return sorted(selection, key=lambda item: (item['index'], item.get('start', -1)))


def project(context, selection, selective):
    sources = [source_excerpt(context['sources'][item['index']], item) for item in ordered(selection)]
    # Keep source order, including native header / recent / tail placements.
    result = {**context, 'sources': sources}
    if selective:
        result['memory_guidance'] = SUMMARY_GUIDANCE if any('summary_version_id' in source for source in sources) else GUIDANCE
    return result


def query_text(context):
    direction = context.get('director_direction', '')
    targets = [source['text'] for source in context['sources'] if source['kind'] in {'draft', 'proposed checked scene'}]
    plans = [encode(context[key]) for key in ('chosen_option', 'proposed_beats', 'approved_beats') if context.get(key)]
    recent = [source['text'] for source in context['sources'] if eligible(source)][-3:]
    focus = direction or '\n'.join(targets)[-12000:]
    return focus, '\n'.join([direction, *targets, *plans])[-12000:] + '\n' + '\n'.join(recent)[-4000:]


def candidates(context, included, settings, aids):
    chunks = [chunk for index, source in enumerate(context['sources']) if eligible(source) and index not in included
              for chunk in compile_chunks(str(index), source['title'], source['text'], source['kind'])]
    excluded = excluded_chunks(context)
    chunks = [chunk for chunk in chunks if chunk_key(context['sources'][int(chunk.source_id)]['id'], chunk.start, chunk.end, chunk.digest) not in excluded]
    corpus = Corpus([with_aid(chunk, source_aid(context['sources'][int(chunk.source_id)], chunk, aids)) for chunk in chunks])
    direction, query = query_text(context)
    directed = corpus.search(direction, limit=settings.recall_limit)
    current = corpus.search(query, limit=settings.recall_limit * 2)
    threads = open_thread_hits(corpus, context) if settings.open_threads else []
    seen, result = set(), []
    for hit in [*directed[:4], *current[:2], *threads, *directed[4:], *current[2:]]:
        if hit.chunk.id not in seen:
            seen.add(hit.chunk.id)
            result.append(hit)
    return result


def open_thread_hits(corpus, context):
    threads = [decode(source['text']) for source in context['sources'] if source['kind'] == 'accepted continuity']
    active = [entry for entry in threads if entry['kind'] == 'thread' and entry['status'] == 'active']
    return [hit for entry in active[-4:]
            for hit in corpus.search(entry['subject'] + ' ' + entry['text'], limit=1)]


def add_recent(context, selection, history, prompt, target):
    included = {item['index'] for item in selection if 'start' not in item}
    for index in reversed(history):
        if index in included or context['sources'][index]['id'].removeprefix('message:') in excluded_nodes(context):
            continue
        trial = [item for item in selection if item['index'] != index] + [whole(index, 'Recent accepted context')]
        if token_estimate(prompt, project(context, trial, True)) > target:
            break
        selection[:] = trial


def add_recall(context, selection, prompt, target, settings, aids):
    included = {item['index'] for item in selection}
    selected_ids = set()
    carried = {source['id'] for source in context['sources']}
    recall_aids = aids if settings.summary_recall else {}
    for hit in candidates(context, included, settings, recall_aids):
        if not anchor_present(hit, selected_ids):
            continue
        item = {'index': int(hit.chunk.source_id), 'start': hit.chunk.start, 'end': hit.chunk.end,
                'sha256': hit.chunk.digest, 'reason': hit.reason,
                'matched_terms': list(hit.matched), 'score': round(hit.score, 6), **neighbor_receipt(hit)}
        aid = source_aid(context['sources'][item['index']], hit.chunk, aids)
        if aid and not hit.anchor_id:
            if settings.summary_recall:
                item['reviewed_aid'] = aid
            exact = source_excerpt(context['sources'][item['index']], item)
            if settings.summary_context and smaller_summary(exact, aid):
                item.update(reviewed_aid=aid, reviewed_summary=True)
        if source_excerpt(context['sources'][item['index']], item)['id'] in carried:
            continue
        if token_estimate(prompt, project(context, [*selection, item], True)) <= target:
            selection.append(item)
            selected_ids.add(hit.chunk.id)
        if len(selected_ids) >= settings.recall_limit:
            break


def receipt(context, packet, selection, allowance, margin, selective):
    _, history = required_positions(context['sources'])
    included = {item['index'] for item in selection if 'start' not in item}
    aided = any('reviewed_aid' in item for item in selection)
    summarized = [item for item in selection if item.get('reviewed_summary')]
    carried_count = sum('summary_version_id' in context['sources'][index] for index in included)
    algorithm = 'prospero-source-reviewed-v6' if aided else 'prospero-source-lexical-v5'
    return {'algorithm': 'prospero-source-summaries-v7' if summarized else algorithm,
            'receipt_version': 3 if summarized else (2 if aided else 1), 'mode': 'long',
            'input_allowance': allowance, 'overhead_margin': margin, 'selective': selective,
            'selection': ordered(selection), 'content_sha256': hashlib.sha256(encode(packet).encode()).hexdigest(),
            'coverage': {'history_sources': len(history), 'included_history': len(included & set(history)),
                         'recalled_passages': sum('start' in item for item in selection) - len(summarized),
                         **({'summarized_passages': len(summarized) + carried_count} if summarized or carried_count else {}),
                         'complete_history': set(history) <= included}}


def assemble_sources(context, prompt, profiles, policy, summary_aids=None):
    settings = memory_settings(policy)
    if settings.mode != 'long' or context.get('scope') == 'blind':
        return context, None
    allowance = min(profile['config']['context_tokens'] - profile['config']['max_output_tokens'] for profile in profiles)
    margin = min(512, max(128, allowance // 50))
    target = allowance - margin
    if token_estimate(prompt, context) <= target and not excluded_chunks(context):
        selection = [whole(index, 'Complete permitted context') for index in range(len(context['sources']))]
        return context, receipt(context, context, selection, allowance, margin, False)
    required, history = required_context(context)
    selection = [whole(index, 'Required working material') for index in sorted(required)]
    minimum = token_estimate(prompt, project(context, selection, True))
    require(minimum <= target, 'The exact working material, guidance and references exceed this model allowance. '
            'Choose a narrower review target, shorter scene or larger context profile. Long Story Memory cannot omit these sources.', 409)
    add_recent(context, selection, history, prompt, minimum + (target - minimum) * 0.55)
    add_recall(context, selection, prompt, target, settings, (summary_aids or {}) if settings.summary_recall or settings.summary_context else {})
    add_recent(context, selection, history, prompt, target)
    packet = project(context, selection, True)
    return packet, receipt(context, packet, selection, allowance, margin, True)
