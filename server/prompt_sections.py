"""Freeze resolved sections separately from the author's role prompt."""
from server.database import decode
from server.manifests import manifest_view
from server.roles import role_key
from server.story_mode import reserved_agency, story_mode

SECTION_ROLES = {'writer', 'scene-plan', 'scene-draft', 'scene-dialogue', 'scene-patch', 'review-informed'}


def sections_for(connection, role, story, manifest_id=None):
    from server.prompts import original_prompt

    settings = decode(story['settings'])
    if role_key(role) not in SECTION_ROLES or settings.get('prompt_sections') is False:
        return []
    # A blind specialist mapped to review-blind never receives persona or agency context.
    items = manifest_view(connection, manifest_id or story['manifest_id'])
    persona = next((item['version']['name'] for item in items if item['enabled'] and item['kind'] == 'persona'),
                   'the character voiced by role user')
    keys = [f'section:mode-{story_mode(settings)}',
            'section:agency-reserved' if reserved_agency(settings) else 'section:agency-shared']
    result = []
    for key in keys:
        prompt = original_prompt(connection, key, story)
        result.append({'id': prompt['id'], 'key': key, 'user_character': persona,
                       'template': prompt['template'].replace('{user_character}', persona)})
    return result


def compose(prompt, sections=()):
    mode = [item['template'] for item in sections if item['key'].startswith('section:mode-')]
    agency = [item['template'] for item in sections if item['key'].startswith('section:agency-')]
    return '\n\n'.join([*mode, prompt['template'], *agency])


def system_prompt(snapshot):
    return compose(snapshot['prompt'], snapshot.get('prompt_sections', []))
