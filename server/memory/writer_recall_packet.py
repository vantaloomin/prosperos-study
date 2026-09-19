"""Pack exact search hits without increasing the frozen writer input allowance."""
from copy import deepcopy
from itertools import zip_longest

from server.database import decode, encode
from server.memory.budget import token_estimate
from server.memory.chunks import Chunk
from server.memory.packet import ordered_layers
from server.memory.recall import unique_hits
from server.memory.retrieval import Corpus
from server.memory.writer_recall import MAX_READS, digest, writer_prompt


def search_sources(sources, queries):
    if not queries:
        return []
    chunks = [Chunk(row['id'], row['source_id'], row['title'], row['text'], row['start'], row['end'],
                    row['sha256'], row['kind']) for row in sources]
    corpus = Corpus(chunks)
    ranked = [corpus.search(query, limit=MAX_READS) for query in queries]
    return unique_hits([hit for group in zip_longest(*ranked) for hit in group if hit])[:MAX_READS]


def make_room(packet, prompt, target, protected):
    """Changes apply to a trial copy, so a rejected hit never displaces context."""
    removed = []
    while token_estimate(prompt, packet) > target:
        old = next((row for row in reversed(packet.get('recalled_passages', [])) if row['id'] not in protected), None)
        if old:
            packet['recalled_passages'].remove(old)
        else:
            old = next((row for row in packet['history'][:-3] if row['role'] != 'ooc' and row['id'] not in protected), None)
            if not old:
                return False, []
            packet['history'].remove(old)
        removed.append(old['id'])
    return True, removed


def include_hit(packet, item, prompt, target, protected):
    trial = deepcopy(packet)
    # An original replaces only its own reviewed interpretation.
    if 'reviewed_summaries' in trial:
        trial['reviewed_summaries'] = [row for row in trial['reviewed_summaries']
                                      if any(row[key] != item[key] for key in ('source_id', 'start', 'end', 'sha256'))]
        if not trial['reviewed_summaries']:
            del trial['reviewed_summaries']
    trial.setdefault('recalled_passages', []).append(item)
    fits, removed = make_room(trial, prompt, target, protected | {item['id']})
    return (trial, removed) if fits else (None, [])


def pack_recall(snapshot, queries, semantic=None):
    if snapshot['writer_recall']['version'] >= 2:
        from server.memory.group_packet import pack_groups
        return pack_groups(snapshot, queries, semantic)
    return pack_v1(snapshot, queries)


def pack_v1(snapshot, queries):
    packet = decode(snapshot['content'])
    memory = snapshot['memory']
    prompt = snapshot['prompt']['template']
    target = memory['input_allowance'] - memory['overhead_margin']
    allowance = min(1600, target // 5)
    sources = snapshot['writer_recall']['sources']
    by_id = {row['id']: row for row in sources}
    selected, decisions, displaced, spent = [], [], [], 0
    for hit in search_sources(sources, queries):
        item = {**by_id[hit.chunk.id], 'reason': 'Prewriting search'}
        fate = hit_fate(packet, item, spent, allowance)
        if not fate:
            trial, removed = include_hit(packet, item, prompt, target, {row['id'] for row in selected})
            if trial is not None:
                packet = trial
                spent += token_estimate('', item)
                displaced.extend(removed)
                selected.append({'id': item['id'], 'source_id': item['source_id'], 'reason': item['reason'],
                                 'matched_terms': list(hit.matched), 'score': round(hit.score, 6)})
            fate = 'selected' if trial is not None else 'input budget'
        decisions.append({'id': item['id'], 'source_id': item['source_id'], 'fate': fate})
    final = finish_packet(snapshot, packet, selected)
    return {'queries': queries, 'decisions': decisions, 'displaced_ids': displaced,
            'evidence_tokens': spent, 'evidence_allowance': allowance, 'final_input': final}


def hit_fate(packet, item, spent, allowance):
    included = {f"message:{node['id']}" for node in packet['history']}
    present = {row['id'] for row in packet.get('recalled_passages', [])}
    if item['source_id'] in included or item['id'] in present:
        return 'already supplied'
    if spent + token_estimate('', item) > allowance:
        return 'recall budget'
    return ''


def finish_packet(snapshot, packet, selected, *, changed=False):
    # With no inserted evidence, retain the original bytes and receipt exactly.
    if not selected and not changed:
        return {key: snapshot[key] for key in ('content', 'memory', 'coverage', 'estimated_input_tokens')}
    packet.setdefault('recalled_passages', []).sort(key=lambda row: (row['passage_number'], row['start']))
    packet = ordered_layers(packet)
    memory = deepcopy(snapshot['memory'])
    kept = {row['id'] for row in packet['recalled_passages']}
    memory['selected'] = [row for row in memory['selected'] if row['id'] in kept] + selected
    summaries = packet.get('reviewed_summaries', [])
    retained = {row['id'] for row in summaries}
    if 'summary_context' in memory:
        memory['summary_context'] = [row for row in memory['summary_context'] if row['id'] in retained]
    if 'summary_aids' in memory:
        memory['summary_aids'] = [row for row in memory['summary_aids'] if row['chunk_id'] in kept]
    if not summaries and memory['algorithm'] == 'prospero-lexical-v7-summary-context':
        memory.pop('summary_context', None)
        memory.update(algorithm='prospero-lexical-v6-reviewed-aids' if 'summary_aids' in memory else 'prospero-lexical-v6',
                      receipt_version=3 if 'summary_aids' in memory else 2)
    coverage = {**memory['coverage'], 'included_messages': len(packet['history']),
                'complete_path': len(packet['history']) == memory['coverage']['messages'],
                'recalled_passages': len(kept), 'summarized_messages': len({row['source_id'] for row in summaries})}
    content = encode(packet)
    memory.update(coverage=coverage, content_sha256=digest(content))
    return {'content': content, 'memory': memory, 'coverage': coverage,
            'estimated_input_tokens': token_estimate(writer_prompt(snapshot), packet)}


def final_snapshot(snapshot, final_input):
    result = {**snapshot, **final_input}
    if 'summary_links' in result:
        ids = {row['id'] for row in decode(result['content']).get('reviewed_summaries', [])}
        result['summary_links'] = [row for row in result['summary_links'] if row['id'] in ids]
    return result
