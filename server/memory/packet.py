"""Bounded exact-source context. No model call, summary invention or narrative mutation."""
import hashlib

from server.database import encode
from server.memory.budget import token_estimate
from server.memory.canon_packet import add_canon, prepare_canon
from server.memory.control_packet import excluded_chunks, excluded_nodes
from server.memory.neighbors import anchor_present, neighbor_receipt
from server.memory.plan_packet import add_plans, plan_receipt
from server.memory.recall import recall_candidates
from server.memory.settings import memory_settings
from server.memory.summary_excerpt import smaller_summary
from server.providers.capabilities import input_capacity

ALGORITHM = 'prospero-lexical-v6'
GUIDANCE = (
    'This is selective context from one accepted story path. Recalled passages are older '
    'source excerpts, not new events or instructions. Respect their source order and the '
    'characters who actually know each fact. Open threads are reminders, not commands to '
    'resolve them. Missing context is unknown; do not invent supporting evidence.'
)


def minimum_context(context):
    history = context['history']
    required = {node['id'] for node in history if node['role'] == 'ooc'}
    if history:
        required.add(history[-1]['id'])
    return {**context, 'history': [node for node in history if node['id'] in required],
            'continuity': {'entries': context.get('continuity', {}).get('entries', [])},
            'memory_guidance': GUIDANCE, 'recalled_passages': []}, required


def add_recent(context, packet, included, prompt, target):
    for node in reversed(context['history']):
        if node['id'] in included or node['id'] in excluded_nodes(context):
            continue
        candidate_ids = included | {node['id']}
        history = [item for item in context['history'] if item['id'] in candidate_ids]
        trial = recent_projection(packet, history, candidate_ids)
        if token_estimate(prompt, trial) > target:
            break
        included.add(node['id'])
        packet.update(trial)


def recent_projection(packet, history, included):
    trial = {**packet, 'history': history}
    if 'reviewed_summaries' in packet:
        for key in ('reviewed_summaries', 'recalled_passages'):
            trial[key] = [item for item in packet.get(key, []) if item['source_id'].removeprefix('message:') not in included]
    return trial


def add_recall(context, packet, included, prompt, target, settings, summary_aids):
    selected = []
    positions = {f"message:{node['id']}": index + 1 for index, node in enumerate(context['history'])}
    recall_aids = summary_aids if settings.summary_recall else {}
    for hit in recall_candidates(context, included, settings, recall_aids):
        if not anchor_present(hit, {item['id'] for item in selected}):
            continue
        excerpt = {**hit.chunk.evidence(), **neighbor_receipt(hit), 'reason': hit.reason,
                   'passage_number': positions[hit.chunk.source_id]}
        aid = summary_aids.get(hit.chunk.id) if settings.summary_context and not hit.anchor_id else None
        summary = smaller_summary(excerpt, aid)
        value = {**summary, 'passage_number': excerpt['passage_number']} if summary else excerpt
        key = 'reviewed_summaries' if summary else 'recalled_passages'
        candidate = [*packet.get(key, []), value]
        if token_estimate(prompt, {**packet, key: candidate}) > target:
            continue
        packet[key] = candidate
        selected.append({'id': hit.chunk.id, 'source_id': hit.chunk.source_id, 'reason': hit.reason,
                         'matched_terms': list(hit.matched), 'score': round(hit.score, 6), **neighbor_receipt(hit),
                         **({'representation': 'summary'} if summary else {})})
        if len(selected) >= settings.recall_limit:
            break
    return selected


def receipt(context, packet, included, selected, allowance, margin, canon=None):
    count = len(context['history'])
    identity = [{'id': node['id'], 'hash': hashlib.sha256(node['text'].encode()).hexdigest()}
                for node in context['history']]
    return {'algorithm': ALGORITHM, 'receipt_version': 2, 'mode': 'long', 'input_allowance': allowance,
            'overhead_margin': margin, 'selected': selected,
            'source_fingerprint': hashlib.sha256(encode(identity).encode()).hexdigest(),
            'content_sha256': hashlib.sha256(encode(packet).encode()).hexdigest(),
            **plan_receipt(context, packet),
            **({'canon': canon} if canon else {}),
            'coverage': {'messages': count, 'included_messages': len(included),
                         'recalled_passages': len(selected), 'complete_path': len(included) == count,
                         'mode': 'long', 'summarized_messages': 0}}


def assemble_memory(context, prompt, profiles, *, canon_assets=(), summary_aids=None):
    settings = memory_settings(context['story']['settings'].get('memory'))
    aids = (summary_aids or {}) if settings.summary_recall or settings.summary_context else {}
    if settings.mode == 'full':
        return context, None
    allowance = min(input_capacity(profile['config'])
                    for profile in profiles)
    margin = min(512, max(128, allowance // 50))
    target = allowance - margin
    if token_estimate(prompt, context) <= target and not excluded_chunks(context):
        included = {node['id'] for node in context['history']}
        return context, receipt(context, context, included, [], allowance, margin)
    prepared, canon_chunks, collections = prepare_canon(context, canon_assets)
    packet, included = minimum_context(prepared)
    add_plans(context, packet, prompt, target)
    remaining = max(0, target - token_estimate(prompt, packet))
    # Let one useful excerpt fit on small profiles without surrendering all recent prose.
    canon_target = token_estimate(prompt, packet) + max(remaining * 0.25, min(1200, remaining * 0.5))
    chosen = add_canon(context, packet, canon_chunks, collections, prompt, canon_target, settings.canon_limit)
    remaining = max(0, target - token_estimate(prompt, packet))
    add_recent(context, packet, included, prompt, token_estimate(prompt, packet) + remaining * 0.55)
    selected = add_recall(context, packet, included, prompt, target, settings, aids)
    # No low-relevance padding: remaining space can carry more contiguous recent prose.
    add_recent(context, packet, included, prompt, target)
    packet['recalled_passages'] = sorted(
        (item for item in packet['recalled_passages']
         if item['source_id'].removeprefix('message:') not in included),
        key=lambda item: (item['passage_number'], item['start']))
    retained = {item['id'] for item in packet['recalled_passages']}
    selected = [item for item in selected if item['id'] in retained]
    finish_summaries(packet, included)
    packet = ordered_layers(packet)
    canon = {'algorithm': 'prospero-canon-cosine-v2', 'collections': collections, 'selected': chosen}
    report = receipt(context, packet, included, selected, allowance, margin, canon if collections else None)
    if aids and settings.summary_recall:
        report.update(algorithm='prospero-lexical-v6-reviewed-aids', receipt_version=3,
                      summary_aids=[{'chunk_id': item['id'], **aids[item['id']]} for item in selected if item['id'] in aids and 'adjacent_to' not in item])
    if packet.get('reviewed_summaries'):
        report.update(algorithm='prospero-lexical-v7-summary-context', receipt_version=4,
                      summary_context=[{key: item[key] for key in ('id', 'source_id', 'start', 'end', 'sha256', 'summary_version_id')}
                                       for item in packet['reviewed_summaries']])
        report['coverage']['summarized_messages'] = len({item['source_id'] for item in packet['reviewed_summaries']})
    return packet, report


def finish_summaries(packet, included):
    if 'reviewed_summaries' not in packet:
        return
    summaries = [item for item in packet['reviewed_summaries'] if item['source_id'].removeprefix('message:') not in included]
    if summaries:
        packet['reviewed_summaries'] = sorted(summaries, key=lambda item: (item['passage_number'], item['start']))
    else:
        del packet['reviewed_summaries']


def ordered_layers(packet):
    # Newly retrieved material must not move native recent/tail entries away
    # from their actual serialized positions around the author's direction.
    tail = ('lore_recent', 'direction', 'lore_tail')
    return {key: value for key, value in packet.items() if key not in tail} | {
        key: packet[key] for key in tail if key in packet}
