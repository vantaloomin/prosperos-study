"""Templates materialize Story switches; workspace switches remain the ceiling."""
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field

from server.database import decode, encode, now, one
from server.errors import require
from server.models import Input
from server.roles import LEGACY_KEYS, ROLE_LABELS
from server.story_mode import story_mode

STORY_AGENTS = (set(ROLE_LABELS) | set(LEGACY_KEYS)) - {
    'library-assist', 'authoring-draft', 'authoring-critique', 'authoring-tighten',
}
TEMPLATES = {
    'passive': [],
    'active': ['scene-options', 'scene-beats', 'scene-draft', 'scene-dialogue',
               'review-blind', 'review-informed', 'scene-triage', 'scene-patch', 'scene-continuity'],
}
router = APIRouter(prefix='/api')


def validate_agent_settings(settings):
    disabled = settings.get('disabled_prompts', [])
    require(isinstance(disabled, list) and all(isinstance(key, str) and key in STORY_AGENTS for key in disabled),
            'Choose supported Story agents and tasks.')
    require(len(disabled) == len(set(disabled)), 'Choose each Story agent once.')
    require(type(settings.get('prompt_sections', True)) is bool, 'Mode guidance must be on or off.')
    template = settings.get('agent_template')
    if template is not None:
        require(isinstance(template, dict) and set(template) == {'mode', 'version', 'customized'}
                and template['mode'] in TEMPLATES and template['version'] == 1
                and type(template['customized']) is bool, 'Unknown Agent Template version.')
    return settings


def apply_template(settings, mode, disabled=None):
    values = sorted(TEMPLATES[mode] if disabled is None else disabled)
    return {**settings, 'disabled_prompts': values,
            'agent_template': {'mode': mode, 'version': 1, 'customized': values != sorted(TEMPLATES[mode])}}


def initial_agent_settings(settings):
    validate_agent_settings(settings)
    if 'disabled_prompts' in settings:
        return settings
    mode = story_mode(settings)
    result = apply_template(settings, mode)
    if mode == 'active':
        result.setdefault('response_length', 'Flexible — stop when the next meaningful move belongs to the user.')
    return result


class StoryAgentsUpdate(Input):
    expected_revision: int = Field(ge=0)
    disabled: list[str] = Field(max_length=100)
    template: Literal['active', 'passive'] | None = None
    prompt_sections: bool = True


@router.get('/agent-templates')
def templates():
    return [{'mode': key, 'version': 1, 'disabled': sorted(value)} for key, value in TEMPLATES.items()]


@router.put('/stories/{story_id}/agents')
def update_story_agents(story_id: str, body: StoryAgentsUpdate, request: Request):
    from server.stories import Stories, check_revision

    with request.app.state.database.connect(write=True) as connection:
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (story_id,))
        check_revision(story, body.expected_revision)
        settings = decode(story['settings'])
        mode = body.template or (settings.get('agent_template') or {}).get('mode')
        settings = apply_template(settings, mode, body.disabled) if mode else {**settings, 'disabled_prompts': body.disabled}
        settings['prompt_sections'] = body.prompt_sections
        validate_agent_settings(settings)
        connection.execute('UPDATE stories SET settings=?,revision=revision+1,updated_at=? WHERE id=?',
                           (encode(settings), now(), story_id))
    return Stories(request.app.state.database).detail(story_id)
