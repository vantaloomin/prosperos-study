"""Explicit source choices from the accepted path and enabled, pinned editions."""
from server.manifests import manifest_view
from server.memory.chunks import compile_chunks
from server.memory.prose_sources import source_chunks, source_evidence

CHARACTER_FIELDS = ('text', 'voice', 'behavior_rules', 'scenario', 'example_dialogue', 'address', 'pronouns')


def pinned_items(connection, branch):
    return [item for item in manifest_view(connection, branch['manifest_id']) if item['enabled']]


def characters(items):
    return [{'id': item['asset_id'], 'name': item['version']['name'], 'version_id': item['version_id']}
            for item in items if item['kind'] in {'character', 'persona'}]


def library_sources(items):
    for item in items:
        version = item['version']
        fields = ('text',) if item['kind'] == 'lorebook' else CHARACTER_FIELDS
        kind = 'Canon reference' if item['kind'] == 'lorebook' else 'Character reference'
        for field in fields:
            text = version['content'].get(field, '')
            if not isinstance(text, str):
                continue
            source_id = f"version:{version['id']}:field:{field}"
            for chunk in compile_chunks(source_id, version['name'], text, kind=kind):
                yield {**chunk.evidence(), 'asset_id': item['asset_id'], 'version_id': version['id'],
                       'field': field, 'edition': version['number'], 'name': version['name']}


def available_sources(connection, branch, include_library=False):
    prose = [source_evidence(node, chunk) for node, chunk in source_chunks(connection, branch['head_id'])]
    return [*prose, *library_sources(pinned_items(connection, branch))] if include_library else prose


def entry_available(entry, path, pins, character_ids):
    if entry.get('character_id') and entry['character_id'] not in character_ids:
        return False
    return all(source_available(source, path, pins) for source in entry['sources'])


def source_available(source, path, pins):
    if 'node_id' in source:
        return source['node_id'] in path
    return (source['asset_id'], source['version_id']) in pins


def partition_entries(connection, branch, entries, path):
    needs_library = any(entry.get('character_id') or any('version_id' in source for source in entry['sources']) for entry in entries)
    items = pinned_items(connection, branch) if needs_library else []
    pins = {(item['asset_id'], item['version_id']) for item in items}
    character_ids = {item['id'] for item in characters(items)}
    available, unavailable = [], []
    for entry in entries:
        target = available if entry_available(entry, path, pins, character_ids) else unavailable
        target.append(entry)
    return available, unavailable
