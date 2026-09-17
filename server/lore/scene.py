import hashlib

from server.lore.placement import placed_sources


def planned_sources(run, sources):
    plan = (run['state'].get('gate_a') or {}).get('mechanics')
    if not plan or not run['snapshot'].get('lore_context', {}).get('books'):
        return sources
    selections = []
    if plan['inherited']:
        selections.append(('opening', 'Prepared opening', plan['inherited']['result'].get('lore', {})))
    selections.extend((item['beat_id'], item['title'], item['result'].get('lore', {})) for item in plan['entries'])
    selected = []
    for beat_id, title, lore in selections:
        for source in lore.get('sources', []):
            source_id = hashlib.sha256(f"{beat_id}:{source['id']}".encode()).hexdigest()
            selected.append({**source, 'id': f'planned:{source_id}',
                'title': f"{title} · {source['title']}", 'scope': 'Reference for this planned beat only; not an accepted event.'})
    context = [source for source in sources if source['kind'] != 'world reference']
    return placed_sources(context, {'sources': selected})
