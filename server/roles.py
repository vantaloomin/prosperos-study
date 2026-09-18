"""Routable roles and their stable task identities.

Task keys remain valid for saved jobs, explicit overrides and exact retries. A role
default is inherited only when a task has no intentional configuration of its own.
"""

ROLES = [
    {'key': 'writer', 'name': 'Primary prose', 'scope': 'writer'},
    {'key': 'collaborator', 'name': 'Collaborator', 'scope': 'side conversation'},
    {'key': 'scene-plan', 'name': 'Scene planner', 'scope': 'scene planning'},
    {'key': 'scene-draft', 'name': 'Scene draft', 'scope': 'approved plan and sources'},
    {'key': 'scene-dialogue', 'name': 'Dialogue writer', 'scope': 'scoped dialogue'},
    {'key': 'review-blind', 'name': 'Independent reader', 'scope': 'blind'},
    {'key': 'review-informed', 'name': 'Informed reader', 'scope': 'informed'},
    {'key': 'scene-triage', 'name': 'Review triage', 'scope': 'reports and primary sources'},
    {'key': 'scene-patch', 'name': 'Revision patch', 'scope': 'approved changes'},
    {'key': 'scribe', 'name': 'Scribe', 'scope': 'recorded text and proposed bookkeeping'},
    {'key': 'library-assist', 'name': 'Library assistant', 'scope': 'library authoring'},
]
ROLE_LABELS = {role['key']: role['name'] for role in ROLES}
BLIND_LENSES = ('plausibility', 'cuts', 'dialogue', 'genre', 'patterns', 'pacing', 'counterpoint', 'setting')
INFORMED_LENSES = ('rules', 'continuity', 'coverage')
TASKS = {
    'scene-options': ('scene-plan', 'task', 'options'),
    'scene-beats': ('scene-plan', 'task', 'beats'),
    'background-interpretation': ('scene-plan', 'task', 'background'),
    'scene-continuity': ('scribe', 'task', 'continuity'),
    'memory-summary': ('scribe', 'task', 'summary'),
    'authoring-enrich': ('scribe', 'task', 'canon-aids'),
    'beat-assessment': ('scribe', 'task', 'beat'),
    'authoring-draft': ('library-assist', 'action', 'draft'),
    'authoring-critique': ('library-assist', 'action', 'critique'),
    'authoring-tighten': ('library-assist', 'action', 'tighten'),
}
LEGACY_KEYS = {
    **{key: key for key in ('writer', 'collaborator', 'scene-draft', 'scene-dialogue', 'scene-triage', 'scene-patch')},
    **{key: task[0] for key, task in TASKS.items()},
    **{f'review-{lens}': 'review-blind' for lens in BLIND_LENSES},
    'review-rules': 'review-informed', 'review-continuity': 'review-informed',
    'scene-coverage': 'review-informed', 'scene-verify': 'scene-triage',
    'scene-dialogue-patch': 'scene-patch',
    'scene-brief': None, 'scene-patch-check': None,
}
RETIRED_STAGES = {'scene-brief', 'scene-coverage', 'scene-verify', 'scene-dialogue-patch', 'scene-patch-check'}


def role_key(key):
    return LEGACY_KEYS.get(key) or key


def task_keys(key):
    return [task for task, role in LEGACY_KEYS.items() if role == key and task != key]


def configured_profile(settings, key):
    overrides = settings.get('step_profiles', {})
    return overrides.get(key) or overrides.get(role_key(key))


def task_context(key, context):
    """Add an explicit discriminator without losing task-specific instructions."""
    if key not in TASKS:
        return context
    _, field, value = TASKS[key]
    result = dict(context)
    if field in result and result[field] != value:
        result[f'{field}_direction'] = result[field]
    result[field] = value
    return result
