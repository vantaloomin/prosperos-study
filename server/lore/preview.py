"""Isolated rule simulation: this module cannot write database or live RNG state."""
from server.lore.engine import initial_lore, select_lore


def preview_lore(body):
    book = {'asset_id': 'preview', 'version_id': 'preview', 'name': 'Draft book',
            'random_stream': 'isolated-preview', 'definition': body.definition.model_dump()}
    state = initial_lore()
    state['clock'] = max(0, body.completed_beats - len(body.prior_passages))
    history, timeline = [], []
    for index, passage in enumerate(body.prior_passages):
        history.append({'role': 'narrator', 'text': passage})
        scan = select_lore([book], history, state, body.master_rng, True, f'{body.seed}:{index}')
        state = scan['after']
        timeline.append(scan)
    state['clock'] = body.completed_beats
    history.append({'role': 'narrator', 'text': body.passage})
    result = select_lore([book], history, state, body.master_rng, True, f'{body.seed}:current')
    return {**result, 'timeline': timeline, 'isolated': True,
            'notice': 'Simulation only. No Story history, live rolls, cooldowns or accepted context changed.'}
