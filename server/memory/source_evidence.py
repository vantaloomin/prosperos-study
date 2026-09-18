"""Carry cited working evidence through review, triage and patch handoffs."""


def cited_ids(value):
    if isinstance(value, list):
        return set().union(*(cited_ids(item) for item in value))
    if isinstance(value, dict):
        own = {value['source_id']} if isinstance(value.get('source_id'), str) else set()
        return own | set().union(*(cited_ids(item) for key, item in value.items() if key != 'sources'))
    return set()


def carry_evidence(sources, cited, available):
    present = {source['id'] for source in sources}
    additions = [{**source, 'kind': 'review evidence'} for source in available
                 if source['id'] in cited and source['id'] not in present]
    if not additions:
        return sources
    # A native tail entry stays at the end of the actual serialized source list.
    position = next((index for index, source in enumerate(sources) if source.get('placement') == 'tail'), len(sources))
    return [*sources[:position], *{source['id']: source for source in additions}.values(), *sources[position:]]


def quotation_matches(source, quote):
    """A derived interpretation cannot masquerade as an exact prose quotation."""
    texts = source['grounding_quotes'] if 'summary_version_id' in source else [source['text']]
    return any(quote in text for text in texts)
