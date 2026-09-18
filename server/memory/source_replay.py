"""Validate archived selective inputs without reranking or changing provider bytes."""
import hashlib

from server.database import decode
from server.errors import require
from server.memory.neighbor_replay import validate_neighbors
from server.memory.scoped_aids import chunk_key, validate_aid
from server.memory.source_packet import eligible, project, required_context


def valid_span(item, source):
    start, end = item.get('start'), item.get('end')
    require(eligible(source) and type(start) is int and type(end) is int
            and 0 <= start < end <= len(source['text']), 'A memory excerpt has an invalid source or span.')
    digest = hashlib.sha256(source['text'][start:end].encode()).hexdigest()
    require(digest == item.get('sha256'), 'A memory excerpt no longer matches its exact source.')
    if 'reviewed_aid' in item:
        validate_aid(item['reviewed_aid'], source['text'][start:end])


def validate_selection(context, memory):
    require(isinstance(memory, dict) and type(memory.get('selective')) is bool, 'Invalid source memory receipt.')
    supported = {('prospero-source-lexical-v1', 1), ('prospero-source-reviewed-v2', 2),
                 ('prospero-source-lexical-v3', 1), ('prospero-source-reviewed-v4', 2),
                 ('prospero-source-lexical-v5', 1), ('prospero-source-reviewed-v6', 2),
                 ('prospero-source-summaries-v7', 3)}
    require((memory.get('algorithm'), memory.get('receipt_version')) in supported
            and context.get('scope') != 'blind', 'Unsupported or out-of-scope source memory receipt.')
    selection = memory.get('selection')
    require(isinstance(selection, list), 'The source memory receipt has no selection.')
    full, spans, order = set(), {}, []
    for item in selection:
        require(isinstance(item, dict), 'Invalid source memory selection.')
        require('reviewed_summary' not in item or (item['reviewed_summary'] is True and 'start' in item and 'reviewed_aid' in item),
                'A reviewed summary lacks its exact source and publication.')
        index = item.get('index')
        require(type(index) is int and 0 <= index < len(context['sources']), 'A memory source is outside the permitted context.')
        order.append((index, item.get('start', -1)))
        if 'start' in item:
            valid_span(item, context['sources'][index])
            spans.setdefault(index, []).append((item['start'], item['end']))
        else:
            require('reviewed_aid' not in item, 'A complete source cannot claim excerpt retrieval provenance.')
            require(index not in full, 'A memory source is duplicated.')
            full.add(index)
    require(order == sorted(order) and not full & spans.keys(), 'Memory sources were reordered or duplicated.')
    aided = any('reviewed_aid' in item for item in selection)
    summaries = any(item.get('reviewed_summary') for item in selection)
    require(summaries == (memory['receipt_version'] == 3) and aided == (memory['receipt_version'] in (2, 3)),
            'Reviewed memory receipt has inconsistent aid provenance.')
    validate_coverage(context, memory, full, spans)
    validate_neighbors(context, selection, memory['algorithm'])
    return selection


def validate_coverage(context, memory, full, spans):
    required, history = required_context(context)
    require(required <= full, 'Source memory omitted required working material or guidance.')
    for ranges in spans.values():
        require(all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:])), 'Memory excerpts overlap.')
    summarized = sum(bool(item.get('reviewed_summary')) for item in memory['selection'])
    carried_count = sum('summary_version_id' in context['sources'][index] for index in full)
    coverage = {'history_sources': len(history), 'included_history': len(full & set(history)),
                'recalled_passages': sum(len(items) for items in spans.values()) - summarized,
                **({'summarized_passages': summarized + carried_count} if summarized or carried_count else {}), 'complete_history': set(history) <= full}
    require(memory.get('coverage') == coverage, 'Memory coverage disagrees with its exact selected sources.')
    require(memory.get('selective') is True or (len(full) == len(context['sources']) and not spans),
            'An incomplete context was labeled complete.')


def replay_sources(context, snapshot, summary_aids=None, canon_assets=None):
    memory = snapshot.get('source_memory')
    if memory is None:
        return context
    require(isinstance(memory, dict), 'Invalid source memory receipt.')
    require(hashlib.sha256(snapshot['content'].encode()).hexdigest() == memory.get('content_sha256'),
            'Saved provider inputs disagree with their memory receipt.')
    if 'canon' in memory:
        from server.memory.source_canon_replay import replay_canon
        context = replay_canon(context, memory['canon'], canon_assets)
    selection = validate_selection(context, memory)
    if summary_aids is not None:
        validate_aid_bindings(context['sources'], selection, summary_aids)
    return project(context, selection, memory['selective'])


def validate_job_projection(expected, snapshot, summary_aids=None, canon_assets=None):
    require(decode(snapshot['content']) == replay_sources(expected, snapshot, summary_aids, canon_assets),
            'A specialist has altered or foreign frozen inputs.')


def validate_aid_bindings(sources, selection, aids):
    for item in selection:
        if 'reviewed_aid' not in item:
            continue
        source_id = sources[item['index']]['id']
        key = chunk_key(source_id, item['start'], item['end'], item['sha256'])
        require(aids.get(key) == item['reviewed_aid'], 'Reviewed recall differs from the scene\'s frozen memory decisions.')
