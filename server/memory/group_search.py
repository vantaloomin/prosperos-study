"""Bounded group discovery; raw passages remain independently searchable."""
from server.memory.chunks import Chunk
from server.memory.evidence_groups import MAX_DEPTH, MAX_GROUPS
from server.memory.retrieval import Corpus
from server.memory.writer_recall import digest

PRIORITY = {'accepted plan': 0, 'derived relationship': 1, 'accepted scene summary': 2, 'reviewed summary': 3}


def discover_groups(groups, queries, hits):
    if not queries:
        return []
    descriptions = Corpus([Chunk(group['id'], group['id'], group['label'], group['description'], 0,
                                 len(group['description']), digest(group['description'])) for group in groups])
    scores = {}
    for query in queries:
        for hit in descriptions.search(query, limit=MAX_GROUPS * 2):
            scores[hit.chunk.id] = max(scores.get(hit.chunk.id, 0), hit.score)
    seeds = {hit.chunk.id for hit in hits}
    chosen, visited = [], set()
    for depth in range(MAX_DEPTH + 1):
        eligible = [group for group in groups if group['id'] not in visited
                    and ((depth == 0 and group['id'] in scores) or seeds.intersection(group['member_ids']))]
        eligible.sort(key=lambda group: (PRIORITY[group['kind']], -scores.get(group['id'], 0), group['id']))
        for group in eligible[:MAX_GROUPS - len(chosen)]:
            chosen.append({**group, 'depth': depth,
                           'trigger': 'description match' if group['id'] in scores else 'linked source'})
            visited.add(group['id'])
        if len(chosen) == MAX_GROUPS or not eligible:
            break
        seeds = {member for group in chosen for member in group['member_ids']}
    return chosen


def candidates(groups, hits, sources):
    indexed = {source['id']: source for source in sources}
    raw = {hit.chunk.id: hit for hit in hits}
    visited, result = set(), []
    members = [(member, group) for group in groups for member in group['member_ids']]
    members.extend((hit.chunk.id, None) for hit in hits)
    for identity, group in members:
        if identity in visited:
            continue
        visited.add(identity)
        hit = raw.get(identity)
        result.append({'source': indexed[identity], 'score': round(hit.score, 6) if hit else 0,
                       'matched_terms': list(hit.matched) if hit else [],
                       'reason': ('Linked evidence: ' + group['label'] if group else
                                  'Combined keyword and semantic search' if hit.reason == 'Combined keyword and semantic search'
                                  else 'Prewriting search')})
    return result
