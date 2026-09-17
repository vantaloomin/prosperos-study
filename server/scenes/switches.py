"""Scene plans freeze workflow choices; skipped checks never become passed checks."""
from server.agent_switches import disabled_agents
from server.scenes.catalog import DRAFT_KEYS, PLAN_KEYS
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.revision_catalog import REVISION_KEYS
from server.workflow.catalog import ROLE_MAP


def scene_switches(connection, story, dialogue_split):
    scene_keys = set(PLAN_KEYS + DRAFT_KEYS + REVISION_KEYS + PATCH_KEYS + CONTINUITY_KEYS) | set(ROLE_MAP)
    disabled = disabled_agents(connection, story).intersection(scene_keys)
    if 'scene-draft' in disabled:
        disabled.update(DRAFT_KEYS + REVISION_KEYS + PATCH_KEYS + CONTINUITY_KEYS)
    if 'scene-beats' in disabled:
        disabled.add('scene-coverage')
    return {'disabled_steps': sorted(disabled),
            'dialogue_split': dialogue_split and 'scene-dialogue' not in disabled}


def enabled_steps(run, keys):
    disabled = set(run['snapshot'].get('disabled_steps', []))
    return [key for key in keys if key not in disabled]


def manual_steps(run):
    relevant = set(DRAFT_KEYS + REVISION_KEYS + PATCH_KEYS + CONTINUITY_KEYS) | set(ROLE_MAP)
    relevant -= set(PLAN_KEYS) | {'scene-draft', 'scene-dialogue'}
    if not run['snapshot'].get('dialogue_split'):
        relevant.discard('scene-dialogue-patch')
    return sorted(relevant.intersection(run['snapshot'].get('disabled_steps', [])))
