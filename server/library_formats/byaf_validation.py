import math
import re
from datetime import datetime

from server.library_formats.containers import member_json, safe_member


def version_one(value, path):
    if type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1:
        raise ValueError(f'{path} must use BYAF schemaVersion 1.')


def text_fields(value, fields, label):
    if any(not isinstance(value.get(field), str) for field in fields):
        raise ValueError(f'{label} is missing required text fields: {", ".join(fields)}.')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('BYAF dates must be ISO timestamps with a timezone.')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('BYAF dates must include a timezone.')


def item_list(value, field, limit, *, minimum=0):
    items = value.get(field)
    if not isinstance(items, list) or not minimum <= len(items) <= limit:
        raise ValueError(f'BYAF {field} must have {minimum}–{limit} entries.')
    return items


def root_documents(members):
    root = member_json(members, 'manifest.json')
    version_one(root, 'manifest.json')
    timestamp(root.get('createdAt'))
    character_path = item_list(root, 'characters', 1, minimum=1)[0]
    safe_member(character_path)
    if not re.fullmatch(r'characters/[^/]+/character\.json', character_path):
        raise ValueError('BYAF character paths must use characters/<id>/character.json.')
    paths = item_list(root, 'scenarios', 32, minimum=1)
    for path in paths:
        safe_member(path)
        if not re.fullmatch(r'scenarios/[^/]+\.json', path):
            raise ValueError('BYAF scenario paths must use scenarios/<name>.json.')
    if len(set(paths)) != len(paths):
        raise ValueError('BYAF scenario references must be distinct.')
    return root, character_path, paths


def validate_character(value, path):
    version_one(value, path)
    text_fields(value, ('id', 'name', 'displayName', 'persona'), path)
    if value['id'] != path.split('/')[1] or not value['name'].strip() or type(value.get('isNSFW')) is not bool:
        raise ValueError('BYAF character identity, name or isNSFW flag is invalid.')
    timestamp(value.get('createdAt'))
    timestamp(value.get('updatedAt'))
    keys = set()
    for item in item_list(value, 'loreItems', 5000):
        if not isinstance(item, dict):
            raise ValueError('BYAF lore items must contain text keys and values.')
        text_fields(item, ('key', 'value'), 'lore item')
        if item['key'] in keys:
            raise ValueError('BYAF lore keys must be distinct.')
        keys.add(item['key'])
    item_list(value, 'images', 64)


def validate_scenario(value, path):
    version_one(value, path)
    text_fields(value, ('narrative', 'formattingInstructions'), path)
    for field in ('minP', 'temperature', 'repeatPenalty', 'repeatLastN', 'topK', 'topP'):
        if type(value.get(field)) not in (int, float) or not math.isfinite(value[field]):
            raise ValueError(f'BYAF {field} must be a finite number.')
    if any(type(value.get(key)) is not bool for key in ('minPEnabled', 'canDeleteExampleMessages')):
        raise ValueError('BYAF sampling and example-message flags must be booleans.')
    template = value.get('promptTemplate')
    if 'promptTemplate' not in value or not isinstance(template, (str, type(None))):
        raise ValueError('BYAF promptTemplate must be a supported string or null.')
    if template not in {None, 'general', 'ChatML', 'Llama3', 'Gemma2', 'CommandR', 'MistralInstruct'}:
        raise ValueError('This BYAF promptTemplate variant is unsupported.')
    if 'grammar' not in value or not isinstance(value['grammar'], (str, type(None))):
        raise ValueError('BYAF grammar must be text or null.')
    for field, limit in (('firstMessages', 1), ('exampleMessages', 5000)):
        validate_examples(item_list(value, field, limit))
    for message in item_list(value, 'messages', 5000):
        validate_message(message)


def validate_examples(items):
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('BYAF example/opening messages must be objects.')
        text_fields(item, ('characterID', 'text'), 'opening/example')


def validate_message(value):
    if not isinstance(value, dict) or not isinstance(value.get('type'), str) or value['type'] not in {'ai', 'human'}:
        raise ValueError('BYAF messages must be ai or human records.')
    items = item_list(value, 'outputs', 100, minimum=1) if value['type'] == 'ai' else [value]
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('BYAF message outputs must be objects.')
        text_fields(item, ('text',), 'message')
        timestamp(item.get('createdAt'))
        timestamp(item.get('updatedAt'))
        if value['type'] == 'ai':
            timestamp(item.get('activeTimestamp'))
