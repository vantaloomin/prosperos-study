"""Pinned lore inputs and beat receipts; read paths never draw or save state."""
import hashlib

from server.branches import path_nodes
from server.lore.engine import initial_lore, select_lore
from server.manifests import manifest_view
from server.mechanics.engine import eligible
from server.mechanics.models import Beat
from server.mechanics.state import node_state


def frozen_lore(connection, branch, history=None):
    books = []
    for item in manifest_view(connection, branch['manifest_id']):
        definition = item['version']['content'].get('lore_definition')
        if item['enabled'] and item['kind'] == 'lorebook' and definition and definition['entries']:
            books.append({'asset_id': item['asset_id'], 'version_id': item['version_id'],
                'source_version_id': item['version_id'], 'priority': item['priority'],
                'random_stream': hashlib.sha256(item['version_id'].encode()).hexdigest(),
                'name': item['version']['name'], 'definition': definition})
    history = path_nodes(connection, branch['head_id']) if history is None and books else history or []
    return {'version': 1, 'books': books, 'history': scan_history(books, history)}


def scan_history(books, history):
    depth = max((book['definition']['scan_messages'] for book in books), default=0)
    prose = [node for node in history if node['role'] != 'ooc'][-depth:] if depth else []
    return [{'role': node['role'], 'text': node['text']} for node in prose]


def current_lore(connection, branch, rng=False, history=None):
    frozen = frozen_lore(connection, branch, history)
    state = node_state(connection, branch['head_id']).get('lore', initial_lore())
    return frozen, select_lore(frozen['books'], frozen['history'], state, rng=rng)


def attach_lore(result, frozen):
    """Extend a newly recorded opportunity; legacy receipts are never retrofitted."""
    if not frozen['books']:
        return result
    before = result['before'].get('lore', initial_lore())
    selection = select_lore(frozen['books'], frozen['history'], before,
        rng=result['settings']['enabled'], advance=eligible(Beat.model_validate(result['beat'])) is None,
        seed=result['seed'])
    result.update(lore_context=frozen, lore=selection)
    result['after'] = {**result['after'], 'lore': selection['after']}
    return result


def selected_for_writer(current, opportunity):
    # A receipt without lore predates this feature. Do not invent a retroactive roll.
    return opportunity['snapshot'].get('lore', current) if opportunity else current
