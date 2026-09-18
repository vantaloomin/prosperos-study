"""Author decisions guide narration; they do not establish fictional events."""

GUIDANCE = (
    'These are explicit author decisions, separate from accepted continuity and Canon. '
    'Keep character knowledge distinct from author/reader knowledge. A belief can be false; '
    'unaware or uncertain characters must not act on information without a supplied learning event. '
    'Conflicting accounts remain unresolved unless the author has labeled a resolution. '
    'Do not invent a resolution, revelation or offscreen event. Evidence supports inspection, '
    'not automatic truth. Emphasis controls style and recall; it does not change the manuscript.'
)


def decision_packet(view):
    entries = [entry for entry in view['entries'] if entry['enabled']]
    if not entries:
        return None
    return {'version_id': view['applied_version_id'], 'authority': GUIDANCE,
            'entries': [packet_entry(entry) for entry in entries]}


def packet_entry(entry):
    if entry['kind'] == 'emphasis' and entry['stance'] == 'exclude':
        return {**entry, 'sources': [{key: source[key] for key in ('id', 'node_id', 'start', 'end', 'sha256')}
                                    for source in entry['sources']],
                'rule': 'Exclude these spans from discretionary Long story recall. Exact targets, current head and required evidence take precedence.'}
    return entry


def excluded_chunks(context):
    entries = context.get('author_memory', {}).get('entries', [])
    return {source['id'] for entry in entries if entry['kind'] == 'emphasis' and entry['stance'] == 'exclude'
            for source in entry['sources']}


def excluded_nodes(context):
    entries = context.get('author_memory', {}).get('entries', [])
    return {source['node_id'] for entry in entries if entry['kind'] == 'emphasis' and entry['stance'] == 'exclude'
            for source in entry['sources']}


def with_decisions(context, snapshot):
    if snapshot.get('author_memory') and context.get('scope') != 'blind':
        return {**context, 'author_memory': snapshot['author_memory']}
    return context
