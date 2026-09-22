"""Compile the complete recipe before any job, draw, publication or text change."""
from copy import deepcopy

from server.database import one
from server.errors import require
from server.providers.capabilities import input_capacity
from server.stories import check_revision
from server.text_edits.selection import apply_selection
from server.text_edits.targets import check_current
from server.workflow.context import snapshot_hash
from server.writing.context import references
from server.writing.recipe_context import compile_job
from server.writing.recipe_settings import chance_spec, execution_steps, execution_story
from server.writing.recipe_sources import source_bundle
from server.writing.recipe_templates import templates_for
from server.writing.resolution import resolve


def prepare_recipe(connection, branch_id, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    require(body.target.story_id == story['id'] and body.target.branch_id in {None, branch_id},
            'The recipe target must belong to its selected Story and telling.', 409)
    target = check_current(connection, body.target, body.expected_version)
    apply_selection(target['text'], body.selection, body.action, '')
    guidance = resolve(connection, story['id'], body.writing)
    require(guidance['recipe'] is not None, 'Choose a published recipe before preparing its workflow.', 409)
    require(guidance['resolved_recipe']['purpose'] == 'draft' or bool(body.selection.text.strip()),
            'Select nonblank prose to review or revise.', 409)
    effective, switches = execution_story(connection, story, guidance['recipe'], body)
    sources = source_bundle(connection, branch, story, target)
    steps = execution_steps(guidance, body)
    plan = []
    for step in steps:
        templates = templates_for(connection, effective, step, sources, switches['effective_disabled'])
        plan.append({'task': step['task'], 'templates': templates,
                     'skipped': not templates, 'reason': 'All selected reader tasks or lenses are disabled.' if not templates else ''})
    require(any(step['templates'] for step in plan), 'Every step in this recipe is disabled.', 409)
    return {'protocol': 1, 'branch': branch, 'story_revision': story['revision'], 'target': target,
            'selection': body.selection.model_dump(), 'action': body.action, 'direction': body.direction,
            'guidance': guidance, 'writing_versions': references(guidance), 'switches': switches,
            'sources': sources, 'plan': plan, 'chance': chance_spec(connection, sources['boundary'], story, guidance, body)}


def public_profile(profile):
    return {key: value for key, value in profile.items() if key != 'credential_ref'}


def recipe_preview(snapshot):
    first = next(index for index, step in enumerate(snapshot['plan']) if step['templates'])
    jobs = [compile_job(snapshot, template, None) for template in snapshot['plan'][first]['templates']]
    chance_pending = snapshot['chance']['applicable'] and snapshot['chance']['beat'] is not None
    exact = not chance_pending
    plan = []
    for index, step in enumerate(snapshot['plan']):
        requests = []
        for position, template in enumerate(step['templates']):
            ready = jobs[position] if index == first else None
            requests.append({'step': template['step'], 'task': template['task'], 'scope': template['scope'],
                             'profile': public_profile(template['profile']), 'profile_source': template['profile_source'],
                             'prompt_version': template['prompt']['number'], 'instructions': template['instructions'],
                             'task_instructions': template['task_instructions'], 'reader': template['reader'],
                             'input_allowance': input_capacity(template['profile']['config']),
                             'output_limit': template['profile']['config']['max_output_tokens'],
                             'estimated_input_tokens': ready['estimated_input_tokens'] if ready else None,
                             'source_memory': ready['source_memory'] if ready else None,
                             'content': ready['content'] if ready else None, 'exact': bool(ready and exact),
                             'awaiting': 'Recorded chance result' if ready and chance_pending else 'Earlier recipe output' if ready is None else None})
        plan.append({**{key: step[key] for key in ('task', 'skipped', 'reason')}, 'requests': requests})
    chance = deepcopy(snapshot['chance'])
    chance['tables'] = {key: {field: value[field] for field in ('id', 'number', 'definition')} for key, value in chance['tables'].items()}
    return {'preview_hash': snapshot_hash(snapshot), 'target': snapshot['target'], 'selection': snapshot['selection'],
            'action': snapshot['action'], 'writing': snapshot['guidance'], 'switches': snapshot['switches'], 'plan': plan,
            'chance': chance, 'maximum_calls': sum(len(step['requests']) for step in plan), 'provider_cost': None,
            'notice': 'Each later step is explicitly previewed using the preceding result before it is sent. '
                      'Review findings and text proposals do not apply edits, accept prose or change Story settings.'}
