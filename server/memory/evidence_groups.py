"""Derive retrieval groups from recorded evidence without changing narrative state."""
from collections import defaultdict

from server.memory.chunks import compile_chunks
from server.memory.writer_recall import digest

MAX_GROUPS = 4
MAX_MEMBERS = 32
MAX_DEPTH = 2
GROUP_RULE = (
    'These links help read recorded source evidence together. They do not create events, resolve '
    'contradictions, or grant character knowledge. Earlier plan evidence can describe superseded '
    'intentions: the accepted current plan remains authoritative. Complete means only that the '
    'known recorded members are supplied, not that every relevant event in the story was found.'
)


class CitationCatalog:
    def __init__(self, history, sources):
        self.allowed = {item['id']: item for item in sources}
        self.nodes = {node['id']: node for node in history if node['role'] != 'ooc'}
        self.ranges, self.chunks = {}, {}
        for position, node in enumerate(history, start=1):
            if node['role'] != 'ooc':
                self.add_node(node, position)

    def add_node(self, node, position):
        source_id = f"message:{node['id']}"
        self.ranges[source_id] = (node['id'], 0, len(node['text']))
        chunks = compile_chunks(source_id, f"{node['role']} passage", node['text'])
        self.chunks[node['id']] = chunks
        for chunk in chunks:
            self.ranges[chunk.id] = (node['id'], chunk.start, chunk.end)
        author_id = f"passage:{position}:{digest(node['text'])}"
        for chunk in compile_chunks(author_id, f'Passage {position}', node['text']):
            self.ranges[chunk.id] = (node['id'], chunk.start, chunk.end)

    def evidence(self, citation, commit):
        source = citation['source_id']
        bounds = self.ranges.get(source)
        if source == 'scene:checked' and commit.get('scene_id') and commit['node_id'] in self.nodes:
            node = self.nodes[commit['node_id']]
            bounds = (node['id'], 0, len(node['text']))
        if bounds is None:
            return set(), 1
        node_id, start, end = bounds
        text, quote = self.nodes[node_id]['text'], citation['quote']
        spans = quotation_spans(text, quote, start, end)
        matched = {chunk.id for chunk in self.chunks[node_id]
                   if any(chunk.start < stop and chunk.end > begin for begin, stop in spans)}
        missing = len(matched - self.allowed.keys()) if matched else 1
        return matched & self.allowed.keys(), missing + int(len(spans) > MAX_MEMBERS)


def quotation_spans(text, quote, start, end):
    spans = []
    while quote and start < end and len(spans) <= MAX_MEMBERS:
        found = text.find(quote, start, end)
        if found < 0:
            break
        spans.append((found, found + len(quote)))
        start = found + 1
    return spans


def group_record(identity, kind, label, description, members, unavailable, sources):
    ordered = [source['id'] for source in sources if source['id'] in members]
    return {'id': identity, 'kind': kind, 'label': label[:300], 'description': description[:6000],
            'member_ids': ordered[:MAX_MEMBERS], 'unavailable_evidence': unavailable,
            'omitted_members': max(0, len(ordered) - MAX_MEMBERS)}


def plan_groups(context, sources, catalog):
    histories = defaultdict(list)
    for commit in context.get('continuity', {}).get('commits', []):
        for change in commit['changes']:
            if change['kind'] == 'plan':
                identity = change['target_id'] or f"{commit['origin_id']}:{change['id']}"
                histories[identity].append((commit, change))
    groups = []
    for entry in context.get('continuity', {}).get('entries', []):
        if entry['kind'] != 'plan':
            continue
        members, unavailable = set(), 0
        for commit, change in histories[entry['id']]:
            for citation in change['evidence']:
                found, missing = catalog.evidence(citation, commit)
                members.update(found)
                unavailable += missing
        if members:
            description = entry['subject'] if unavailable else entry['subject'] + ' ' + entry['text']
            groups.append(group_record('plan:' + entry['id'], 'accepted plan', entry['subject'],
                                       description, members, unavailable, sources))
    return groups


def scene_groups(context, sources, catalog):
    groups = []
    for commit in context.get('continuity', {}).get('commits', []):
        chunks = catalog.chunks.get(commit['node_id'], ())
        members = {chunk.id for chunk in chunks}
        # A scene description can reveal any part of its source; exclude it if any part is blocked.
        if not commit.get('summary') or not members or not members <= catalog.allowed.keys():
            continue
        source_id = chunks[0].source_id
        groups.append(group_record('scene-summary:' + source_id, 'accepted scene summary',
                                   'Accepted scene description', commit['summary'], members, 0, sources))
    return groups


def freeze_groups(context, sources, summary_aids):
    catalog = CitationCatalog(context['history'], sources)
    groups = [*plan_groups(context, sources, catalog), *scene_groups(context, sources, catalog)]
    for chunk_id, aid in summary_aids.items():
        if chunk_id not in catalog.allowed or aid['source_sha256'] != catalog.allowed[chunk_id]['sha256']:
            continue
        description = ' '.join((aid['summary'], *aid['topics'], *aid['aliases']))
        groups.append(group_record('reviewed:' + chunk_id, 'reviewed summary', 'Reviewed source description',
                                   description, {chunk_id}, 0, sources))
    return groups
