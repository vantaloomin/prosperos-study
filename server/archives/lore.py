"""Replay lore receipts and remap state identities without editing provider inputs."""
from server.database import decode, one
from server.errors import require
from server.lore.engine import initial_lore, select_lore
from server.lore.placement import group
from server.lore.runtime import attach_lore, frozen_lore
from server.mechanics.state import node_state


def validate_frozen(connection, branch, frozen):
    expected = frozen_lore(connection, branch)
    require(frozen['version'] == 1 and frozen['history'] == expected['history'], 'Lore scan includes altered or unrelated history.')
    omit = {'random_stream', 'source_version_id'}
    def projected(books):
        return [{k: v for k, v in book.items() if k not in omit} for book in books]
    require(projected(frozen['books']) == projected(expected['books']), 'Lore uses different books from its pinned manifest.')
    require(all(book['random_stream'] and book['source_version_id'] for book in frozen['books']), 'Lore source identities are missing.')


def validate_receipt(connection, snapshot):
    if 'lore_context' not in snapshot:
        require('lore' not in snapshot, 'Lore decisions require frozen inputs.')
        return
    validate_frozen(connection, snapshot['branch'], snapshot['lore_context'])
    require(snapshot['before'] == node_state(connection, snapshot['branch']['head_id']), 'Lore beat starts from altered state.')
    expected = dict(snapshot)
    attach_lore(expected, snapshot['lore_context'])
    require(expected.get('lore') == snapshot.get('lore') and expected['after'] == snapshot['after'], 'Lore beat differs from its recorded seed or rules.')


def validate_generation(connection, snapshot):
    if 'lore_context' not in snapshot:
        return
    validate_frozen(connection, snapshot['branch'], snapshot['lore_context'])
    lore = snapshot['lore']
    frozen = snapshot['lore_context']
    before = node_state(connection, snapshot['branch']['head_id']).get('lore', initial_lore())
    expected = select_lore(frozen['books'], frozen['history'], before, rng=lore['rng_enabled'])
    if snapshot.get('opportunity_id'):
        receipt = decode(one(connection, 'SELECT snapshot FROM mechanic_opportunities WHERE id=?', (snapshot['opportunity_id'],))['snapshot'])
        expected = receipt.get('lore', expected)
    require(lore == expected, 'Writer lore differs from its saved branch or beat decision.')
    content = decode(snapshot['content'])
    if lore['entries']:
        require(all(content.get('lore_' + place) == group(lore, place) for place in ('header', 'recent', 'tail')),
                'Writer references differ from the selected lore prose.')


def validate_node_lore(connection, row):
    node = one(connection, 'SELECT * FROM nodes WHERE id=?', (row['node_id'],))
    metadata = decode(node['metadata'])
    expected = node_state(connection, node['parent_id']).get('lore')
    if metadata.get('opportunity_id'):
        receipt = decode(one(connection, 'SELECT snapshot FROM mechanic_opportunities WHERE id=?', (metadata['opportunity_id'],))['snapshot'])
        expected = receipt['after'].get('lore')
    if metadata.get('source') == 'accepted_scene':
        scene = decode(one(connection, 'SELECT state FROM scene_runs WHERE id=?', (metadata['scene_id'],))['state'])
        schedule = scene['gate_a'].get('mechanics')
        expected = schedule['after'].get('lore') if schedule else expected
    require(decode(row['state']).get('lore') == expected, 'Accepted lore state differs from its branch receipt.')


def validate_lore(connection, data):
    for row in data['mechanic_opportunities']:
        validate_receipt(connection, decode(row['snapshot']))
    for row in data['generations']:
        validate_generation(connection, decode(row['snapshot']))
    for row in data['scene_runs']:
        snapshot = decode(row['snapshot'])
        if 'lore_context' in snapshot:
            validate_frozen(connection, snapshot['branch'], snapshot['lore_context'])
    for row in data['node_mechanics']:
        validate_node_lore(connection, row)


def remap_lore(value, mapping):
    """Only explicit catalog identities change; citation IDs and entry IDs stay exact."""
    if isinstance(value, list):
        return [remap_lore(item, mapping) for item in value]
    if not isinstance(value, dict):
        return value
    return {key: mapping.get(item, item) if key in {'asset_id', 'version_id'} and isinstance(item, str)
            else remap_lore(item, mapping) for key, item in value.items()}


def remap_state(value, mapping):
    result = dict(value)
    if 'last_opportunity_id' in value:
        result['last_opportunity_id'] = mapping.get(value['last_opportunity_id'], value['last_opportunity_id'])
    if 'lore' in value:
        result['lore'] = remap_lore(value['lore'], mapping)
    return result
