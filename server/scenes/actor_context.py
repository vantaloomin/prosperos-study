"""Independent dialogue writers with explicit, frozen character evidence."""
import hashlib

from server.database import decode, encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.control_sources import characters, pinned_items
from server.memory.control_state import controls_at
from server.memory.knowledge import prepare_knowledge
from server.profiles import resolve_profile
from server.prompts import prompt_snapshot

ACTOR_RULE = (
    'Fill only your assigned dialogue slots. The author briefing is explicitly shared '
    'proposed scene information, not an accepted event. No other actor response, full '
    'scene plan, narration, private background or chance receipt has been shared. '
    'Do not infer those hidden inputs. A matching Character ID keeps its identity '
    'even if an older evidence decision records another name.'
)


def frozen_controls(connection, run):
    origin = run['snapshot']
    return controls_at(connection, origin['branch'], origin.get('memory_controls_version_id'))


def actor_choices(connection, run):
    controls = frozen_controls(connection, run)
    names = {item['id']: item['name'] for item in characters(pinned_items(connection, run['snapshot']['branch']))}
    choices = {}
    for entry in controls['entries']:
        if entry['kind'] != 'knowledge' or not entry['enabled']:
            continue
        character_id = entry.get('character_id')
        key = 'character:' + character_id if character_id else 'name:' + entry['subject']
        choices[key] = {'key': key, 'subject': names.get(character_id, entry['subject']), 'character_id': character_id}
    return list(choices.values())


def actor_frame(subject, slot_ids):
    return {'stage': 'scene-dialogue', 'actor_rule': ACTOR_RULE, 'sources': [],
            'skeleton': {'summary': 'Only explicitly assigned dialogue slots.', 'proposed_facts': [],
                         'blocks': [{'id': key, 'kind': 'dialogue', 'speaker': subject,
                                     'instruction': 'Use only the author briefing and your granted evidence.'} for key in slot_ids]}}


def check_assignments(context, actors):
    slots = [block['id'] for block in context['skeleton']['blocks'] if block['kind'] == 'dialogue']
    selected = [key for actor in actors for key in actor.slot_ids]
    require(len(selected) == len(set(selected)) and set(selected) == set(slots),
            'Assign every dialogue slot exactly once before previewing character writers.', 409)
    return slots


def prepare_actor(connection, run, actor, slots, controls, prompt, profiles):
    choices = actor_choices(connection, run)
    key = 'character:' + actor.character_id if actor.character_id else 'name:' + actor.subject
    chosen = next((item for item in choices if item['key'] == key), None)
    require(chosen, 'This character view is not available in the scene’s frozen knowledge. Start a new scene to use newer decisions.', 409)
    ordered = [key for key in slots if key in actor.slot_ids]
    frame = actor_frame(chosen['subject'], ordered)
    writing = run['snapshot']['story_context']['constraints']
    base, receipt, links = prepare_knowledge(controls, chosen['subject'], actor.briefing,
        prompt['template'] + encode(frame), profiles, writing, actor.character_id)
    content = encode({**decode(base), **frame})
    cost = token_estimate(prompt['template'], decode(content))
    require(cost <= receipt['input_allowance'] - receipt['overhead_margin'], 'The character briefing and complete evidence exceed this context allowance.', 409)
    return {'branch': run['snapshot']['branch'], 'memory_controls_version_id': controls['version_id'],
            **({'knowledge_character_id': actor.character_id} if actor.character_id else {}),
            'knowledge_content': base, 'knowledge_lens': receipt, 'source_links': links,
            'slot_ids': ordered, 'content': content, 'estimated_input_tokens': cost,
            'content_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}


def actor_jobs(connection, story, run, body, context):
    require(body.key == 'scene-dialogue', 'Character writers currently apply to the dialogue stage only.')
    require(len(body.profile_ids) == len(set(body.profile_ids)), 'Choose each comparison profile once.')
    profiles = [resolve_profile(connection, story, body.key, key) for key in (body.profile_ids or [None])]
    prompt = prompt_snapshot(connection, body.key, story)
    slots = check_assignments(context, body.dialogue_actors)
    controls = frozen_controls(connection, run)
    actors = [prepare_actor(connection, run, actor, slots, controls, prompt, profiles) for actor in body.dialogue_actors]
    return [{'step': body.key, 'profile': profile, 'prompt': prompt, 'content': encode(context),
             'dialogue_actors': actors, 'estimated_input_tokens': sum(actor['estimated_input_tokens'] for actor in actors)} for profile in profiles]


def actor_preview(job):
    return [{'subject': actor['knowledge_lens']['subject'], 'slot_ids': actor['slot_ids'],
             'estimated_input_tokens': actor['estimated_input_tokens'], 'knowledge_lens': actor['knowledge_lens'],
             'content': actor['content'], 'instructions': job['prompt']['template']} for actor in job.get('dialogue_actors', [])]
