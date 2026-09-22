"""Resolve new writing requests while retaining historical input shapes by default."""
from server.errors import require
from server.writing.pins import read_pins
from server.writing.resolution import resolve


def request_guidance(connection, story, body, *, purpose='draft', task='writer'):
    choices = getattr(body, 'writing', None)
    pins = read_pins(connection, story['id'])
    if choices is None and pins['style'] == pins['recipe'] == 'none':
        return None
    result = resolve(connection, story['id'], choices)
    if not result['style'] and not result['recipe']:
        return None
    recipe = result['resolved_recipe']
    if recipe:
        require(recipe['purpose'] == purpose, f'Choose a {purpose} recipe for this writing action.', 409)
        require(task not in recipe['disabled_tasks'], 'This writing task is disabled for the recipe.', 409)
        require(all(step['task'] == task for step in recipe['steps']),
                'This recipe needs the review/revision workflow, which is not available yet. '
                f'Choose a recipe containing only the {task} task for this action.', 409)
        require(recipe['randomness'] is None,
                'Recipe randomness overrides are not available yet. Remove the override before '
                'using this recipe for this writing action; existing Story chance controls still apply.', 409)
    return result


def writer_profiles(explicit, guidance, task='writer'):
    if explicit or not guidance or not guidance['resolved_recipe']:
        return explicit
    writer = next((step for step in guidance['resolved_recipe']['steps'] if step['task'] == task), None)
    return [writer['profile_id']] if writer and writer['profile_id'] else []


def references(guidance):
    return [guidance[key]['id'] for key in ('style', 'recipe') if guidance.get(key)] if guidance else []
