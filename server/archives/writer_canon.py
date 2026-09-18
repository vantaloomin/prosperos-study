"""Verify writer Canon against the immutable manifest, including selective overviews."""
from server.archives.writer_sources import validate_selection
from server.character_content import narrative_asset
from server.errors import require
from server.manifests import manifest_view
from server.memory.canon_compiler import compile_overview
from server.memory.canon_models import canon_policy
from server.memory.canon_packet import KNOWLEDGE, without_overview
from server.memory.source_canon import bound_content


def validate_writer_canon(connection, snapshot, content, identities, *, allow_legacy=False):
    assets = [item for item in manifest_view(connection, snapshot['branch']['manifest_id']) if item['enabled']]
    frozen = content['library']
    require(len(frozen) == len(assets), 'Writer references differ from their pinned manifest.')
    bindings = {live['version_id']: item['version_id'] for live, item in zip(assets, frozen, strict=True)}
    receipt = snapshot['memory'].get('canon')
    items = content.get('recalled_canon', [])
    collections, chunks, bound = [], {}, True
    for live, item in zip(assets, frozen, strict=True):
        matched = identities.matches(live['version_id'], item['version_id']) and identities.matches(live['asset_id'], item['asset_id'])
        require(matched or allow_legacy, 'Writer Canon names a different pinned source identity.')
        bound = bound and matched
        expected = frozen_asset(live, item, bindings)
        relevant = bool(receipt) and live['kind'] == 'lorebook' and canon_policy(live['version']['content']).mode == 'relevant'
        if relevant:
            compiled, report = compile_overview('version:' + item['version_id'], live['version']['name'], live['version']['content'])
            chunks.update({chunk.id: chunk for chunk in compiled})
            collections.append({**report, 'version_id': item['version_id'], 'name': live['version']['name'],
                                'number': live['version']['number'], 'selected_chunks': sum(row['source_id'] == 'version:' + item['version_id'] for row in items)})
            expected = without_overview(expected)
        require(item == expected, 'A writer reference differs from its pinned edition or overview projection.')
    validate_canon_receipt(receipt, items, collections, chunks)
    return bound


def frozen_asset(live, item, bindings):
    value = narrative_asset(live)
    return {**value, 'asset_id': item['asset_id'], 'version_id': item['version_id'],
            'version': {**value['version'], 'id': item['version_id'], 'asset_id': item['asset_id'],
                        'content': bound_content(value['version']['content'], bindings)}}


def validate_canon_receipt(receipt, items, collections, chunks):
    if receipt is None:
        require(not items and not collections, 'Writer Canon excerpts have no selection receipt.')
        return
    require(receipt['algorithm'] == 'prospero-canon-cosine-v2' and bool(collections)
            and receipt['collections'] == collections, 'Writer Canon coverage differs from its pinned compiler inputs.')
    order = []
    for item in items:
        chunk = chunks.get(item['id'])
        require(chunk is not None and item == {**chunk.evidence(), 'knowledge': KNOWLEDGE},
                'A writer Canon excerpt changed its pinned source bytes or authority.')
        order.append((item['source_id'], item['start']))
    require(order == sorted(order), 'Writer Canon excerpts changed source order.')
    validate_selection(items, receipt['selected'])
