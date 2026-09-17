from server.background.targets import interpreted_guidance
from server.mechanics.models import RngSettings
from server.mechanics.randomness import ALGORITHM, Draws
from server.mechanics.table_engine import TableSet, qualitative

AUTHORITY = ('Private potential, not established facts. Respect genre, existing canon and player agency. '
             'Never assign the player unchosen actions, feelings or consent. Do not expose the seed, '
             'table labels or private guidance in summaries. A due hook is an opportunity, not a command '
             'to advance time or force an event. Future hooks remain latent until their Story day; '
             'adapt generic time phrases to that chronology. Only explicitly accepted prose establishes events.')


def resolve_background(recipe, versions, settings, seed):
    tables, draws = TableSet(versions, RngSettings.model_validate(settings)), Draws(seed)
    drives = []
    for index, character in enumerate(recipe['characters']):
        results = [tables.resolve(key, draws, f'drive:{index}:{key}') for key in ('automaton-a', 'automaton-b')]
        drives.append({'character': character, 'results': results})
    hooks = []
    for index in range(recipe['hooks']):
        result = tables.resolve('hooks', draws, f'hook:{index}')
        offset = draws.die(recipe['horizon'], f'date:{index}', 'Story-relative days') if qualitative(result) else None
        hooks.append({'result': result, 'day': recipe['day'] + offset if offset else None})
    return {'algorithm': ALGORITHM, 'seed': seed, 'drives': drives, 'hooks': hooks,
            'draws': draws.log, 'tables': tables.used}


def guidance(snapshot):
    data = snapshot['result']
    drives = [{'character': item['character'], 'cues': [cue for result in item['results'] for cue in (qualitative(result) or [])]}
              for item in data['drives']] if snapshot['drives_enabled'] else []
    hooks = [{'day': item['day'], 'due': item['day'] <= snapshot['day'], 'cues': qualitative(item['result'])}
             for item in data['hooks'] if item['day'] is not None] if snapshot['hooks_enabled'] else []
    return {'authority': AUTHORITY, 'chronology': {'origin': snapshot['recipe']['origin'], 'day': snapshot['day'],
            'unit': 'Story-relative days; no real-world calendar is assumed'}, 'drives': drives, 'hooks': hooks,
            **interpreted_guidance(snapshot)}
