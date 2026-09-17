"""Put selected prose at actual serialized context positions, without rule metadata."""


def group(selection, placement):
    return [source for source in selection['sources'] if source['placement'] == placement]


def writer_context(context, selection):
    if not selection['entries']:
        return context
    content = {key: value for key, value in context.items() if key not in {'direction', 'lore_header', 'lore_recent', 'lore_tail'}}
    return {'lore_header': group(selection, 'header'), **content,
            'lore_recent': group(selection, 'recent'), 'direction': context['direction'],
            'lore_tail': group(selection, 'tail')}


def placed_sources(sources, selection):
    # Reviews put recent references immediately before their draft. Scene plans
    # have no draft yet, so recent references follow accepted context.
    position = next((i for i, source in enumerate(sources) if source['kind'] == 'draft'), len(sources))
    return [*group(selection, 'header'), *sources[:position], *group(selection, 'recent'),
            *sources[position:], *group(selection, 'tail')]
