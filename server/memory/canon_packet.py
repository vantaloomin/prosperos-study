"""Separate Canon retrieval: pinned overviews only, after scope filtering."""
from server.memory.budget import token_estimate
from server.memory.canon_compiler import compile_overview
from server.memory.canon_models import canon_policy
from server.memory.recall import current_query
from server.memory.retrieval import Corpus

KNOWLEDGE = 'World reference; not an accepted event or proof of what any character knows.'


def prepare_canon(context, assets):
    # The caller passes the branch's pinned manifest, not the Library's latest heads.
    permitted = {item['version_id'] for item in context.get('library', [])}
    selected = [item for item in assets if item['enabled'] and item['kind'] == 'lorebook'
                and item['version_id'] in permitted
                and canon_policy(item['version']['content']).mode == 'relevant']
    chunks, collections = [], []
    for item in selected:
        version = item['version']
        compiled, report = compile_overview(f"version:{version['id']}", version['name'], version['content'])
        chunks.extend(compiled)
        collections.append({**report, 'version_id': version['id'], 'name': version['name'],
                            'number': version['number'], 'selected_chunks': 0})
    ids = {item['version_id'] for item in selected}
    library = [without_overview(item) if item['version_id'] in ids else item for item in context.get('library', [])]
    packet = {**context, 'library': library, 'recalled_canon': []} if selected else context
    return packet, chunks, collections


def without_overview(item):
    version = item['version']
    content = {key: value for key, value in version['content'].items() if key != 'text'}
    return {**item, 'version': {**version, 'content': content},
            'overview_coverage': 'Relevant excerpts only; missing details remain unknown.'}


def canon_hits(context, chunks, limit):
    corpus = Corpus(chunks)
    direct = corpus.search(context['direction'], limit=limit, cosine_only=True)
    recent = corpus.search(current_query(context), limit=limit, cosine_only=True)
    # Direct author intent wins ties with ambient recent prose; no cross-story statistics.
    hits = {}
    for hit in [*direct, *recent]:
        hits.setdefault(hit.chunk.id, hit)
    return list(hits.values())


def add_canon(context, packet, chunks, collections, prompt, target, limit):
    selected = []
    by_version = {f"version:{item['version_id']}": item for item in collections}
    for hit in canon_hits(context, chunks, limit):
        item = {**hit.chunk.evidence(), 'knowledge': KNOWLEDGE}
        candidate = [*packet['recalled_canon'], item]
        if token_estimate(prompt, {**packet, 'recalled_canon': candidate}) > target:
            continue
        packet['recalled_canon'] = candidate
        by_version[hit.chunk.source_id]['selected_chunks'] += 1
        selected.append({'id': hit.chunk.id, 'source_id': hit.chunk.source_id,
                         'reason': 'Relevant pinned Canon', 'matched_terms': list(hit.matched),
                         'score': round(hit.score, 6)})
        if len(selected) >= limit:
            break
    if chunks:
        packet['recalled_canon'].sort(key=lambda item: (item['source_id'], item['start']))
    return selected
