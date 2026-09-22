from server.errors import require
from server.prompts import ALL_PROMPT_LABELS
from server.section_prompts import SECTION_LABELS
from server.workflow.readers import lens_task
from server.writing.recipe_settings import expand_disabled


def validate_switches(snapshot):
    switches = snapshot['switches']
    require(set(switches) == {'workspace_disabled', 'story_disabled', 'recipe_disabled', 'run_switches', 'effective_disabled'},
            'A recipe has unsupported task-switch evidence.')
    allowed = set(ALL_PROMPT_LABELS) - set(SECTION_LABELS)
    for key in ('workspace_disabled', 'story_disabled', 'recipe_disabled', 'effective_disabled'):
        values = switches[key]
        require(isinstance(values, list) and len(values) == len(set(values)) and set(values) <= allowed,
                'A recipe contains unsupported or repeated task disables.')
    require(switches['recipe_disabled'] == snapshot['guidance']['recipe']['content']['disabled_tasks'],
            'Recipe task disables differ from their published source.')
    overrides = switches['run_switches']
    require(isinstance(overrides, dict) and set(overrides) <= allowed and all(type(value) is bool for value in overrides.values()),
            'A recipe has invalid run task choices.')
    disabled = set(switches['recipe_disabled']) | set(switches['story_disabled'])
    for key, enabled in overrides.items():
        if enabled:
            disabled.discard(key)
        else:
            disabled.add(key)
    effective = expand_disabled(disabled) | set(switches['workspace_disabled'])
    require(switches['effective_disabled'] == sorted(effective), 'A recipe changed task-switch precedence.')
    for stage in snapshot['plan']:
        for template in stage['templates']:
            keys = {template['step']} | {lens_task(lens) for lens in (template['reader'] or {}).get('lenses') or []}
            require(not keys & effective, 'A recipe schedules a disabled task or reader lens.')
