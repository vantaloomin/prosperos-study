"""An explicit request lens; ordinary writing continues to use its existing context."""
from server.background.storage import state_id
from server.database import decode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.control_sources import characters, pinned_items
from server.memory.control_state import control_view
from server.memory.knowledge import prepare_knowledge
from server.memory.plan_state import plan_head
from server.prompt_sections import compose, sections_for
from server.prompts import prompt_snapshot
from server.writing.context import references


def knowledge_snapshot(connection, branch, story, body, profiles, guidance=None):
    require(not body.use_prepared_beat and not body.assess_beat,
            'Character evidence view cannot include prepared chance or beat assessment. '
            'Turn those off for this request, or return to Author view.', 409)
    controls = control_view(connection, branch)
    subject = body.knowledge_subject
    if body.knowledge_character_id:
        choices = {item['id']: item['name'] for item in characters(pinned_items(connection, branch))}
        require(body.knowledge_character_id in choices, 'This Character is no longer enabled in the Story. Choose its view again.', 409)
        subject = choices[body.knowledge_character_id]
    prompt = prompt_snapshot(connection, 'writer', story)
    sections = sections_for(connection, 'writer', story, branch['manifest_id'])
    instructions = compose(prompt, sections)
    content, report, links = prepare_knowledge(controls, subject, body.direction, instructions, profiles, decode(story['settings']), body.knowledge_character_id, guidance)
    return {'branch': branch, 'story_revision': story['revision'], 'prompt': prompt, 'prompt_sections': sections,
            **({'writing_versions': references(guidance), 'writing_guidance': guidance} if guidance else {}),
            'continuity_version_id': plan_head(connection, branch['id']),
            'memory_controls_version_id': controls['version_id'], 'knowledge_lens': report, 'source_links': links,
            'background_state_id': state_id(connection, branch['id']), 'opportunity_id': None,
            'content': content, 'estimated_input_tokens': token_estimate(instructions, decode(content)),
            **({'knowledge_character_id': body.knowledge_character_id} if body.knowledge_character_id else {}),
            'coverage': {'messages': len({link['node_id'] for link in links if 'node_id' in link}), 'complete_path': False}}, profiles
