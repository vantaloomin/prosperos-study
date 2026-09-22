"""Only these textual leaves are eligible; settings and rule switches are not."""
from copy import deepcopy

from server.character_content import TEXT_FIELDS
from server.errors import require

STYLE_FIELDS = ('prose', 'viewpoint', 'tense', 'dialogue', 'rhythm', 'description', 'avoid')


def field_path(kind, ref, content):
    if ref.kind == 'library-field':
        return library_path(kind, ref, content)
    require(ref.kind == 'writing-field', 'Choose a supported versioned text field.')
    if kind == 'style':
        require(ref.field in STYLE_FIELDS, 'Choose a style guidance field; examples and settings need their own editor.')
        return (ref.field,), 12000
    require(kind == 'recipe', 'Choose a writing style or recipe.')
    if ref.field == 'instructions':
        return ('instructions',), 12000
    require(ref.field == 'step-instructions', 'Only recipe instruction text can be changed by this action.')
    return ('steps', item_index(content.get('steps', []), 'task', ref.item_id), 'instructions'), 12000


def library_path(kind, ref, content):
    if kind in {'character', 'persona'}:
        if ref.field == 'greeting':
            return ('greetings', item_index(content.get('greetings', []), 'id', ref.item_id), 'text'), 100000
        require(ref.field in {*TEXT_FIELDS, 'address', 'pronouns'}, 'Choose a Character text field.')
        return (ref.field,), {'address': 1000, 'pronouns': 300}.get(ref.field, 100000)
    require(kind == 'lorebook', 'Choose a Character or Canon collection.')
    if ref.field == 'text':
        return ('text',), 100000
    require(ref.field == 'entry', 'Only Canon overview or entry text can be changed by this action.')
    entries = content.get('lore_definition', {}).get('entries', [])
    return ('lore_definition', 'entries', item_index(entries, 'id', ref.item_id), 'text'), 100000


def item_index(items, key, identity):
    positions = [index for index, item in enumerate(items) if item.get(key) == identity]
    require(len(positions) == 1, 'This text item is missing or ambiguous in the current edition. Reopen its editor.', 409)
    return positions[0]


def field_text(kind, ref, content):
    path, limit = field_path(kind, ref, content)
    value = content
    for key in path[:-1]:
        value = value[key]
    text = value.get(path[-1], '')
    require(isinstance(text, str) and len(text) <= limit, 'This field is not supported text.')
    return text, limit


def changed_content(kind, ref, content, text):
    path, limit = field_path(kind, ref, content)
    require(len(text) <= limit, 'The replacement exceeds this text field’s limit.')
    result = deepcopy(content)
    destination = result
    for key in path[:-1]:
        destination = destination[key]
    destination[path[-1]] = text
    return result


def field_options(kind, content):
    if kind in {'character', 'persona'}:
        return [(key, None, key.replace('_', ' ').capitalize()) for key in (*TEXT_FIELDS, 'address', 'pronouns')] + [
            ('greeting', item['id'], 'Greeting · ' + item['label']) for item in content.get('greetings', [])]
    if kind == 'lorebook':
        return [('text', None, 'World knowledge · Markdown')] + [('entry', item['id'], 'Entry · ' + item['title'])
            for item in content.get('lore_definition', {}).get('entries', [])]
    if kind == 'style':
        return [(key, None, key.capitalize()) for key in STYLE_FIELDS]
    return [('instructions', None, 'Recipe instructions')] + [('step-instructions', item['task'], item['task'].capitalize() + ' instructions')
        for item in content.get('steps', [])]
