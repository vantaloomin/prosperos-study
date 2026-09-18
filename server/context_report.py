"""Measured application input bytes and explicitly approximate token budgets."""
import hashlib
import json
import math

from server.database import decode, encode
from server.errors import require
from server.section_prompts import SECTION_LABELS

LABELS = {
    'story': 'Story and writing preferences', 'history': 'Selected story path',
    'knowledge_view': 'Character evidence boundary', 'knowledge': 'Permitted character evidence',
    'author_memory': 'Author decisions and supporting evidence',
    'library': 'Pinned Library material', 'direction': 'Direction for this draft',
    'plan_memory': 'Plans and commitments', 'continuity': 'Accepted continuity', 'private_background': 'Private background',
    'memory_guidance': 'How recalled evidence should be used',
    'reviewed_summaries': 'Reviewed summaries in context',
    'recalled_passages': 'Earlier passages recalled for this draft',
    'recalled_canon': 'Recalled Canon references',
    'prepared_beat': 'Prepared narrative beat', 'lore_header': 'Lore before the story',
    'lore_recent': 'Lore near recent context', 'lore_tail': 'Lore after the direction',
}


def input_sections(snapshot):
    """Include JSON keys, separators and braces in the byte accounting."""
    values = list(decode(snapshot['content']).items())
    sections = instruction_sections(snapshot)
    instruction_count = len(sections)
    for index, (key, value) in enumerate(values):
        text = ('{' if index == 0 else ',') + encode(key) + ':' + encode(value)
        text += '}' if index == len(values) - 1 else ''
        sections.append({'key': key, 'label': LABELS.get(key, key), 'text': text,
                         'source_count': len(value) if isinstance(value, list) else 1,
                         'description': section_description(key, value)})
    require(''.join(item['text'] for item in sections[instruction_count:]) == snapshot['content'],
            'This input format cannot be broken down without changing its bytes.', 409)
    return sections


def instruction_sections(snapshot):
    sections = snapshot.get('prompt_sections', [])
    mode = [dict(item, text=item['template'] + '\n\n') for item in sections if item['key'].startswith('section:mode-')]
    agency = [dict(item, text='\n\n' + item['template']) for item in sections if item['key'].startswith('section:agency-')]
    role = {'key': 'prompt', 'label': 'Writer instructions', 'text': snapshot['prompt']['template'],
            'source_count': 1, 'description': f"Prompt v{snapshot['prompt']['number']}"}
    def section(item):
        return {'key': item['key'], 'label': SECTION_LABELS[item['key']], 'text': item['text'],
                'source_count': 1, 'description': 'Versioned mode guidance · ' + item['id']}
    return [*[section(item) for item in mode], role, *[section(item) for item in agency]]


def section_description(key, value):
    if key == 'history':
        return f'{len(value):,} contributions, including any author notes and greetings in this path'
    if key == 'library':
        return f'{len(value):,} enabled, pinned assets; author-only fields and artwork are excluded'
    if key == 'private_background':
        return 'Includes private material. Reveal only if you want to inspect it.'
    return 'Exact application input, including its serialized metadata'


def section_summaries(sections):
    consumed, previous = 0, 0
    result = []
    for section in sections:
        measured = len(section['text'].encode('utf-8'))
        consumed += measured
        estimate = math.ceil(consumed / 3)
        result.append({key: value for key, value in section.items() if key != 'text'} | {
            'bytes': measured, 'estimated_tokens': estimate - previous})
        previous = estimate
    return result


def profile_budget(profile, estimate, overhead=0):
    config = profile['config']
    overhead += config.get('context_safety_tokens', 0)
    reserved = config['max_output_tokens']
    remaining = config['context_tokens'] - estimate - reserved - overhead
    return {'profile_id': profile['profile_id'], 'version_id': profile['id'], 'name': profile['name'],
            'version': profile['number'], 'provider': config['provider'], 'model': config['model'],
            'context_tokens': config['context_tokens'], 'output_tokens': reserved,
            'estimated_input_tokens': estimate, 'remaining_tokens': remaining, 'fits': remaining >= 0,
            **({'overhead_tokens': overhead} if overhead else {})}


def preview_fingerprint(snapshot, budgets, assessment):
    identity = {'branch': snapshot['branch'], 'story_revision': snapshot['story_revision'],
                'prompt': snapshot['prompt'], 'prompt_sections': snapshot.get('prompt_sections', []), 'content': snapshot['content'],
                'budgets': budgets, 'assessment': assessment, 'memory': snapshot.get('memory'),
                'opportunity_id': snapshot.get('opportunity_id'),
                'background_state_id': snapshot.get('background_state_id')}
    return hashlib.sha256(encode(identity).encode('utf-8')).hexdigest()


def source_labels(snapshot, section):
    if section == 'prompt':
        return [f"writer · v{snapshot['prompt']['number']} · {snapshot['prompt']['id']}"]
    context = decode(snapshot['content'])
    if section == 'library':
        return [f"{item['version']['name']} · {item['kind']} · v{item['version']['number']} · {item['version_id']}"
                for item in context.get('library', [])]
    if section == 'history':
        return [f"{index + 1}. {item['role']} · {item['id']}" for index, item in enumerate(context['history'])]
    if section in {'recalled_passages', 'recalled_canon', 'reviewed_summaries'}:
        return [f"{item['source_id']} · characters {item['start']}–{item['end']}"
                for item in context.get(section, [])]
    return []


def readable_section(snapshot, key):
    if key.startswith('section:'):
        return next(item['template'] for item in snapshot.get('prompt_sections', []) if item['key'] == key)
    if key == 'prompt':
        return snapshot['prompt']['template']
    value = decode(snapshot['content'])[key]
    if key == 'reviewed_summaries':
        return '\n\n'.join(readable_summary(item) for item in value)
    if key == 'history':
        return '\n\n'.join(f"### {index + 1}. {node['role']}\nSource: {node['id']}\n\n{node['text']}"
                           for index, node in enumerate(value))
    if key == 'library':
        return '\n\n'.join(readable_asset(item) for item in value)
    if key == 'recalled_canon':
        return '\n\n'.join(f"### {item['title']}\nSource: {item['source_id']} · characters "
                           f"{item['start']}–{item['end']}\n{item['knowledge']}\n\n{item['text']}" for item in value)
    if key == 'recalled_passages':
        return '\n\n'.join(f"### Passage {item['passage_number']} · {item['reason']}\n"
                           f"Source: {item['source_id']} · characters {item['start']}–{item['end']}\n\n"
                           f"{item['text']}" for item in value)
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def readable_asset(item):
    version = item['version']
    heading = f"### {version['name']} · {item['kind']} · v{version['number']}\nVersion: {item['version_id']}"
    fields = [f"{key.replace('_', ' ').capitalize()}\n{value if isinstance(value, str) else encode(value)}"
              for key, value in version['content'].items()]
    return heading + '\n\n' + '\n\n'.join(fields)


def section_page(snapshot, sections, key, offset, view):
    section = next((item for item in sections if item['key'] == key), None)
    require(section is not None, 'This input section is unavailable.', 404)
    value = section['text'] if view == 'exact' else readable_section(snapshot, key)
    require(offset <= len(value), 'This page is outside the input section.')
    sources = source_labels(snapshot, key)
    return {'text': value[offset:offset + 8000], 'offset': offset, 'total_characters': len(value),
            'next_offset': offset + 8000 if offset + 8000 < len(value) else None,
            'sources': sources[:30], 'source_count': len(sources)}


def readable_summary(item):
    return (f"### Reviewed interpretation · Passage {item['passage_number']}\n"
            f"Source: {item['source_id']} · characters {item['start']}–{item['end']}\n"
            f"Summary version: {item['summary_version_id']}\n{item['authority']}\n\n{item['text']}\n\n"
            'Exact grounding quotes:\n' + '\n'.join(f'> {quote}' for quote in item['grounding_quotes']))
