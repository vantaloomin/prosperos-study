"""Retrieve linked originals within the same writer and exact-read budgets."""
from copy import deepcopy

from server.database import decode
from server.memory.budget import token_estimate
from server.memory.evidence_groups import GROUP_RULE
from server.memory.group_search import candidates, discover_groups
from server.memory.hybrid_recall import hybrid_hits
from server.memory.writer_recall import MAX_READS, writer_prompt
from server.memory.writer_recall_packet import (
    finish_packet,
    hit_fate,
    include_hit,
    make_room,
    search_sources,
)


def present_ids(packet, sources):
    whole = {f"message:{node['id']}" for node in packet['history']}
    return {source['id'] for source in sources if source['source_id'] in whole} | {
        row['id'] for row in packet.get('recalled_passages', [])}


def protected_sources(groups, sources):
    members = {member for group in groups for member in group['member_ids']}
    return members | {source['source_id'].removeprefix('message:') for source in sources if source['id'] in members}


def coverage(groups, packet, sources):
    present = present_ids(packet, sources)
    return [{'id': group['id'], 'label': group['label'], 'kind': group['kind'],
             'member_ids': group['member_ids'],
             'supplied_ids': [member for member in group['member_ids'] if member in present],
             'missing_ids': [member for member in group['member_ids'] if member not in present],
             'unavailable_evidence': group['unavailable_evidence'], 'omitted_members': group['omitted_members'],
             'complete': set(group['member_ids']) <= present and not group['unavailable_evidence'] and not group['omitted_members'],
             'trigger': group['trigger'], 'depth': group['depth']}
            for group in groups]


def coverage_note(reports):
    return {'rule': GROUP_RULE, 'groups': [
        {'label': row['label'], 'kind': row['kind'], 'known_passages': len(row['member_ids']) + row['omitted_members'],
         'supplied_passages': len(row['supplied_ids']), 'unavailable_evidence': row['unavailable_evidence'],
         'complete_known_group': row['complete']} for row in reports]}


def reserve_notes(packet, groups, sources, prompt, target, protected_hits=frozenset()):
    trial = deepcopy(packet)
    # Reserve the larger incomplete wording, then replace it with final measured coverage.
    trial['recall_groups'] = coverage_note(coverage(groups, packet, sources))
    for row in trial['recall_groups']['groups']:
        row['complete_known_group'] = False
        row['supplied_passages'] = row['known_passages']
    fits, removed = make_room(trial, prompt, target, protected_sources(groups, sources) | protected_hits)
    return (trial, removed) if fits else (None, [])


def fit_notes(packet, groups, sources, prompt, target, protected_hits=frozenset()):
    retained = list(groups)
    omitted = []
    while retained:
        trial, removed = reserve_notes(packet, retained, sources, prompt, target, protected_hits)
        if trial is not None:
            return trial, retained, omitted, removed
        omitted.append(retained.pop()['id'])
    return packet, [], omitted, []


def add_candidates(snapshot, packet, groups, hits, target, allowance, protected_hits=frozenset()):
    sources = snapshot['writer_recall']['sources']
    selected, decisions, displaced, spent = [], [], [], 0
    protected = protected_sources(groups, sources) | protected_hits
    for candidate in candidates(groups, hits, sources)[:MAX_READS]:
        item = {**candidate['source'], 'reason': candidate['reason']}
        fate = hit_fate(packet, item, spent, allowance)
        if not fate:
            trial, removed = include_hit(packet, item, writer_prompt(snapshot), target, protected | {row['id'] for row in selected})
            if trial is not None:
                packet = trial
                spent += token_estimate('', item)
                displaced.extend(removed)
                selected.append({key: candidate[key] for key in ('score', 'matched_terms', 'reason')} |
                                {'id': item['id'], 'source_id': item['source_id']})
            fate = 'selected' if trial is not None else 'input budget'
        decisions.append({'id': item['id'], 'source_id': item['source_id'],
                          'passage_number': item['passage_number'], 'fate': fate})
    return packet, selected, decisions, displaced, spent


def pack_groups(snapshot, queries, semantic=None):
    packet = decode(snapshot['content'])
    archive = snapshot['writer_recall']
    target = snapshot['memory']['input_allowance'] - snapshot['memory']['overhead_margin']
    allowance = min(1600, target // 5)
    hits = (hybrid_hits(archive['sources'], queries, semantic)
            if archive['version'] >= 3 and queries and semantic and semantic['status'] == 'completed'
            else search_sources(archive['sources'], queries))
    # A query match already supplied is still selected evidence. Later additions
    # and coverage notes must not evict it, including matches visited later in the
    # bounded ranking. Keep the old behavior for frozen v1-v4 requests.
    protected = ({hit.chunk.id for hit in hits} | {hit.chunk.source_id.removeprefix('message:') for hit in hits}
                 if archive['version'] >= 5 else frozenset())
    found = discover_groups(archive['groups'], queries, hits)
    packet, groups, omitted, removed = fit_notes(packet, found, archive['sources'], writer_prompt(snapshot), target, protected)
    packet, selected, decisions, displaced, spent = add_candidates(snapshot, packet, groups, hits, target, allowance, protected)
    reports = coverage(groups, packet, archive['sources'])
    if groups:
        packet['recall_groups'] = coverage_note(reports)
    final = finish_packet(snapshot, packet, selected, changed=bool(groups))
    return {'queries': queries, 'decisions': decisions, 'displaced_ids': [*removed, *displaced],
            'evidence_tokens': spent, 'evidence_allowance': allowance, 'groups': reports,
            'omitted_group_ids': omitted, 'final_input': final}
