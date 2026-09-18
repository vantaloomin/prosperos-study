"""Clearly labeled reviewed interpretations, distinct from exact source excerpts."""
from server.database import encode
from server.memory.chunks import compile_chunks
from server.memory.scoped_aids import chunk_key, validate_aid

KIND = 'reviewed summary'
AUTHORITY = (
    'Reviewed interpretation of older accepted prose; not an exact transcript, new event, '
    'Canon change or grant of character knowledge. Grounding quotes are exact source text. '
    'Other details may be omitted; absence is not evidence of a contradiction. '
    'Citations must quote grounding_quotes, not this interpretation.'
)


def summary_excerpt(source_id, start, end, digest, aid):
    identity = chunk_key(source_id, start, end, digest)
    return {'id': f"summary:{aid['version_id']}:{identity}", 'kind': KIND,
            'title': 'Reviewed interpretation of earlier prose', 'text': aid['summary'],
            'source_id': source_id, 'start': start, 'end': end, 'sha256': digest,
            'summary_version_id': aid['version_id'], 'grounding_quotes': aid['quotes'], 'authority': AUTHORITY}


def smaller_summary(exact, aid):
    if not aid:
        return None
    validate_aid(aid, exact['text'])
    summary = summary_excerpt(exact['source_id'], exact['start'], exact['end'], exact['sha256'], aid)
    if 'passage_number' in exact:
        summary['passage_number'] = exact['passage_number']
    return summary if len(encode(summary).encode()) < len(encode(exact).encode()) else None


def summary_items(content):
    return [*content.get('reviewed_summaries', []),
            *(source for source in content.get('sources', []) if 'summary_version_id' in source or source.get('kind') == KIND or 'grounding_quotes' in source)]


def summary_links(content, frozen=None):
    bindings = {link['id']: link for link in (frozen or [])}
    return [bindings.get(item['id']) or {'id': item['id'], 'version_id': item['summary_version_id'],
             'frozen_version_id': item['summary_version_id'], 'node_id': item['source_id'].removeprefix('message:'),
             'frozen_source_id': item['source_id']} for item in summary_items(content)]


def aid_items(sources, aids):
    return [summary_excerpt(source['id'], chunk.start, chunk.end, chunk.digest, aids[chunk.id])
            for source in sources if source['id'].startswith('message:')
            for chunk in compile_chunks(source['id'], source['title'], source['text']) if chunk.id in aids]
