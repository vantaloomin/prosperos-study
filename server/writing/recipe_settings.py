"""Recipe defaults never mutate the Story; explicit run choices remain bounded."""
from server.agent_switches import disabled_agents
from server.database import decode, encode
from server.errors import require
from server.mechanics.config import configured_tables, parse_settings, read_settings
from server.mechanics.state import node_state
from server.prompts import ALL_PROMPT_LABELS
from server.roles import BLIND_LENSES, INFORMED_LENSES, LEGACY_KEYS
from server.section_prompts import SECTION_LABELS


def expand_disabled(keys):
    return set(keys) | {key for key, role in LEGACY_KEYS.items() if role in keys}


def execution_story(connection, story, recipe, body):
    allowed = set(ALL_PROMPT_LABELS) - set(SECTION_LABELS)
    require(set(body.task_switches) <= allowed, 'Choose supported task switches for this recipe run.')
    settings = decode(story['settings'])
    disabled = set(settings.get('disabled_prompts', [])) | set(recipe['content']['disabled_tasks'])
    for key, enabled in body.task_switches.items():
        if enabled:
            disabled.discard(key)
        else:
            disabled.add(key)
    workspace = disabled_agents(connection)
    effective = expand_disabled(disabled) | workspace
    return {**story, 'settings': encode({**settings, 'disabled_prompts': sorted(effective)})}, {
        'workspace_disabled': sorted(workspace), 'story_disabled': settings.get('disabled_prompts', []),
        'recipe_disabled': recipe['content']['disabled_tasks'], 'run_switches': body.task_switches,
        'effective_disabled': sorted(effective),
    }


def execution_steps(recipe, body):
    content = recipe['resolved_recipe']
    steps = content['steps'] or [{'task': {'draft': 'writer', 'review': 'review', 'revise': 'revision'}[content['purpose']],
                                 'instructions': '', 'profile_id': None, 'lenses': []}]
    tasks = [step['task'] for step in steps]
    purpose = content['purpose']
    if purpose == 'draft':
        require(tasks[0] == 'writer', 'A drafting recipe starts with Draft prose; reviews and revisions can follow.', 409)
    elif purpose == 'review':
        require(tasks == ['review'], 'A review recipe contains only Review prose. Choose Revise for a revision workflow.', 409)
    else:
        require('writer' not in tasks and 'revision' in tasks, 'A revision recipe needs Revise prose, with an optional review.', 409)
    require(not body.review_lenses or 'review' in tasks, 'This recipe has no review step for the selected lenses.')
    require(set(body.profiles) <= set(tasks), 'A model override names a task absent from this recipe.')
    lenses = body.review_lenses
    if lenses is not None:
        require(len(lenses) == len(set(lenses)) and set(lenses) <= set(BLIND_LENSES + INFORMED_LENSES),
                'Choose distinct supported review lenses.')
    return [{**step, 'profile_id': body.profiles.get(step['task'], step['profile_id']),
             'profile_source': 'request' if step['task'] in body.profiles else 'recipe' if step['profile_id'] else 'inherited',
             'lenses': lenses if step['task'] == 'review' and lenses is not None else step['lenses']} for step in steps]


def chance_spec(connection, branch, story, recipe, body):
    authored = recipe['resolved_recipe']['randomness']
    settings = body.randomness or (parse_settings(authored) if authored is not None else read_settings(story))
    source = 'request' if body.randomness is not None else 'recipe' if authored is not None else 'story'
    applicable = recipe['resolved_recipe']['purpose'] == 'draft'
    require(applicable or body.beat is None, 'Chance preparation applies to a new draft, not a review or wording revision.')
    require(applicable or source == 'story' or not settings.enabled,
            'A review or revision cannot introduce new chance events. Turn off this recipe override or inherit the Story setting.', 409)
    require(not (applicable and settings.enabled) or body.beat is not None,
            'Describe the eligible beat before running a draft recipe with chance enabled.', 409)
    require(body.beat is None or settings.enabled, 'Enable chance for this run before supplying a beat.')
    tables = configured_tables(connection, settings)
    require(body.beat is None or set(body.beat.extras) <= set(tables), 'A requested chance table is missing from this run configuration.')
    settings = settings.model_copy(update={'table_versions': {key: value['id'] for key, value in tables.items()}})
    return {'settings': settings.model_dump(), 'source': source, 'applicable': applicable,
            'beat': body.beat.model_dump() if body.beat else None,
            'before': node_state(connection, branch['head_id']), 'tables': tables,
            'automatic_assessment_applicable': False,
            'notice': 'Preview makes no draws. A requested draft run records its own chance result; '
                      'text proposals do not advance Story mechanics or schedule acceptance assessments.'}
