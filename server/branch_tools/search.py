"""Literal Story-wide browsing with source groups and exact telling membership."""
import hashlib
import re
from bisect import bisect_left

from server.branch_tools.curation import story_branches
from server.branch_tools.lineage import StorySources
from server.database import one
from server.errors import require


def branch_search(connection, story_id, body):
    one(connection, 'SELECT id FROM stories WHERE id=?', (story_id,))
    branches = story_branches(connection, story_id)
    require(set(body.branch_ids) <= {row['id'] for row in branches}, 'A search branch belongs to another Story.')
    selected = [row for row in branches if (not body.branch_ids or row['id'] in body.branch_ids)
                and (body.include_archived or not row['curation']['archived'])]
    sources = StorySources(connection, story_id)
    starts, ends = sources.intervals()
    heads = sorted((starts[row['head_id']], row['id'], row) for row in selected if row['head_id'])
    positions = [item[0] for item in heads]
    pattern = re.compile(re.escape(body.query), re.IGNORECASE)
    groups = {}
    for node in sources.nodes.values():
        removed = bool(node['metadata'].get('removed'))
        if removed and not body.include_removed:
            continue
        text = search_text(sources, node, removed)
        match = pattern.search(text)
        if not match:
            continue
        members = heads[bisect_left(positions, starts[node['id']]):bisect_left(positions, ends[node['id']])]
        if not members:
            continue
        add_match(groups, sources, node, text, removed, match.span(), [item[2] for item in members])
    results = list(groups.values())
    results.sort(key=lambda item: (-len(item['occurrences']), item['created_at'], item['group_id']))
    return {'story_id': story_id, 'query': body.query, 'total': len(results), 'searched_branches': len(selected),
            'results': results[body.offset:body.offset + body.limit],
            'next_offset': body.offset + body.limit if body.offset + body.limit < len(results) else None,
            'scope': 'Browsing only. These matches do not expand writer or character knowledge.'}


def search_text(sources, node, removed):
    if not removed:
        return node['text']
    original = sources.nodes.get(node['metadata'].get('original_node_id'))
    return original['text'] if original else ''


def add_match(groups, sources, node, text, removed, span, branches):
    root = sources.original(node['id'])
    key = root, node['role'], text, removed
    if key not in groups:
        start, end = span
        digest = hashlib.sha256((root + '\0' + node['role'] + '\0' + str(removed) + '\0' + text).encode('utf-8')).hexdigest()
        groups[key] = {'group_id': digest, 'original_node_id': root, 'role': node['role'], 'removed': removed,
                       'created_at': node['created_at'], 'before': text[max(0, start - 110):start],
                       'match': text[start:end], 'after': text[end:end + 190],
                       'truncated_before': start > 110, 'truncated_after': end + 190 < len(text), 'occurrences': []}
    groups[key]['occurrences'].extend({'branch_id': branch['id'], 'branch_name': branch['name'],
        'branch_revision': branch['revision'], 'head_id': branch['head_id'], 'node_id': node['id'],
        'archived': branch['curation']['archived'], 'favorite': branch['curation']['favorite']} for branch in branches)
