"""Select explicitly optional Canon before the existing specialist history packet."""
from server.character_content import narrative_asset
from server.database import decode, encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.canon_compiler import compile_overview
from server.memory.canon_models import canon_policy
from server.memory.canon_packet import KNOWLEDGE
from server.memory.retrieval import Corpus
from server.memory.settings import memory_settings
from server.memory.source_evidence import cited_ids
from server.memory.source_packet import project, query_text, required_context, whole

ALGORITHM = 'prospero-specialist-canon-v1'
GUIDANCE = (
    'Selected Canon overviews contain relevant exact Markdown excerpts only. Omitted details '
    'remain unknown. Character definitions, conditional entries and directly cited references '
    'remain complete. Canon describes the world, not accepted events or character knowledge.'
)


def catalog_for(context, assets):
    references = [(i, source) for i, source in enumerate(context['sources']) if source['kind'] == 'reference']
    if not references:
        return {}
    enabled = [item for item in assets if item['enabled']]
    require(len(references) == len(enabled), 'Specialist references disagree with their pinned manifest.')
    cited = cited_ids(context)
    bindings = {item['version_id']: source['id'].removeprefix('asset:')
                for (_, source), item in zip(references, enabled, strict=True)}
    catalog = {}
    for (index, source), item in zip(references, enabled, strict=True):
        # IDs can be frozen from an earlier archive; bind to the ordered, immutable
        # manifest by exact narrative bytes, never by the Library's latest version.
        if item['kind'] != 'lorebook':
            continue
        expected = narrative_asset(item)['version']
        require(source['title'] == expected['name'] and decode(source['text']) == bound_content(expected['content'], bindings),
                'A Canon source differs from its pinned edition.')
        content = item['version']['content']
        if canon_policy(content).mode == 'relevant' and source['id'] not in cited:
            chunks, report = compile_overview(str(index), source['title'], content)
            catalog[index] = {'chunks': chunks, 'report': {**report, 'source_id': source['id'], 'title': source['title']}}
    return catalog


def bound_content(content, bindings):
    if 'lorebook_versions' not in content:
        return content
    return {**content, 'lorebook_versions': [bindings.get(value, value) for value in content['lorebook_versions']]}


def excerpt(source, span):
    text = decode(source['text'])['text'][span['start']:span['end']]
    return {'id': f"{source['id']}@{span['start']}:{span['end']}:{span['sha256'][:12]}",
            'kind': 'Canon excerpt', 'title': source['title'], 'text': text,
            'source_id': source['id'], 'source_field': 'text', 'start': span['start'],
            'end': span['end'], 'sha256': span['sha256'], 'knowledge': KNOWLEDGE}


def project_canon(context, collections):
    by_index = {item['index']: item for item in collections}
    sources = []
    for index, source in enumerate(context['sources']):
        selection = by_index.get(index)
        if selection is None:
            sources.append(source)
            continue
        metadata = {key: value for key, value in decode(source['text']).items() if key != 'text'}
        sources.append({**source, 'text': encode(metadata),
                        'overview_coverage': 'Relevant excerpts only; missing details remain unknown.'})
        sources.extend(excerpt(source, span) for span in selection['spans'])
    return {**context, 'sources': sources, 'canon_guidance': GUIDANCE}


def coverage(collections):
    return {'collections': len(collections), 'available_excerpts': sum(item['chunks'] for item in collections),
            'selected_excerpts': sum(len(item['spans']) for item in collections)}


def required_cost(context, prompt):
    required, history = required_context(context)
    selection = [whole(index, 'Required working material') for index in sorted(required)]
    return token_estimate(prompt, project(context, selection, True)), len(set(history) - required)


def canon_candidates(context, catalog, limit):
    corpus = Corpus([chunk for item in catalog.values() for chunk in item['chunks']])
    direct, recent = query_text(context)
    seen = set()
    for hit in [*corpus.search(direct, limit=limit, cosine_only=True),
                *corpus.search(recent, limit=limit, cosine_only=True)]:
        if hit.chunk.id not in seen:
            seen.add(hit.chunk.id)
            yield hit


def select_excerpts(context, collections, catalog, prompt, target, limit):
    by_index = {item['index']: item for item in collections}
    existing = {source['id'] for source in context['sources']}
    count = 0
    for hit in canon_candidates(context, catalog, limit):
        item = by_index[int(hit.chunk.source_id)]
        span = {'start': hit.chunk.start, 'end': hit.chunk.end, 'sha256': hit.chunk.digest,
                'reason': 'Relevant pinned Canon', 'matched_terms': list(hit.matched), 'score': round(hit.score, 6)}
        if excerpt(context['sources'][item['index']], span)['id'] in existing:
            continue  # A carried citation already supplies these exact bytes as required evidence.
        item['spans'].append(span)
        if required_cost(project_canon(context, collections), prompt)[0] > target:
            item['spans'].pop()
        else:
            count += 1
        if count >= limit:
            break
    for item in collections:
        item['spans'].sort(key=lambda span: span['start'])


def compact_canon(context, prompt, profiles, policy, assets):
    settings = memory_settings(policy)
    if settings.mode != 'long' or context.get('scope') == 'blind' or not assets:
        return context, None
    allowance = min(profile['config']['context_tokens'] - profile['config']['max_output_tokens'] for profile in profiles)
    target = allowance - min(512, max(128, allowance // 50))
    if token_estimate(prompt, context) <= target:
        return context, None
    catalog = catalog_for(context, assets)
    if not catalog:
        return context, None
    collections = [{'index': index, **item['report'], 'spans': []} for index, item in catalog.items()]
    minimum, optional_history = required_cost(project_canon(context, collections), prompt)
    # Share remaining space with accepted history; when there is no optional history,
    # Canon can use the full remainder. Required instructions never become optional.
    share = 0.4 if optional_history else 1.0
    select_excerpts(context, collections, catalog, prompt, minimum + max(0, target - minimum) * share, settings.canon_limit)
    return project_canon(context, collections), {'algorithm': ALGORITHM, 'collections': collections,
                                                'coverage': coverage(collections)}
