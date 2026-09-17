"""Character authoring fields and the subset used for narrative requests."""
from server.database import one
from server.errors import require

AUTHORING_FIELDS = {'greetings', 'author_notes', 'artwork_sha256'}
TEXT_FIELDS = ('text', 'voice', 'behavior_rules', 'scenario', 'example_dialogue', 'author_notes')


def validate_character(content):
    for key in TEXT_FIELDS:
        if key in content:
            require(isinstance(content[key], str) and len(content[key]) <= 100000,
                    f'{key} must be text of at most 100,000 characters.')
    for key, limit in (('address', 1000), ('pronouns', 300)):
        if key in content:
            require(isinstance(content[key], str) and len(content[key]) <= limit, f'{key} must be text of at most {limit} characters.')
    greetings = content.get('greetings', [])
    require(isinstance(greetings, list) and len(greetings) <= 32, 'Use at most 32 opening greetings.')
    seen = set()
    for greeting in greetings:
        validate_greeting(greeting)
        require(greeting['id'] not in seen, 'Each greeting needs a unique ID.')
        seen.add(greeting['id'])


def validate_greeting(value):
    require(isinstance(value, dict), 'Each greeting must have an ID, label, and text.')
    for key, limit in (('id', 100), ('label', 120), ('text', 100000)):
        item = value.get(key)
        require(isinstance(item, str) and 0 < len(item.strip()) <= limit,
                f'Greeting {key} must be nonempty text of at most {limit:,} characters.')


def narrative_asset(item):
    if item['kind'] == 'persona':
        item = {**item, 'kind': 'character'}
    excluded = AUTHORING_FIELDS if item['kind'] == 'character' else {'lore_definition', 'lore_documents', 'artwork_sha256'}
    content = {key: value for key, value in item['version']['content'].items() if key not in excluded}
    return {**item, 'version': {**item['version'], 'content': content}}


def opening_metadata(connection, body):
    from server.library import get_version

    source = body.opening_source
    if source is None:
        return {'source': 'story_opening'}
    require(bool(body.opening_text), 'Choose an opening passage or clear its greeting source.')
    require(any(item.enabled and item.asset_id == source.asset_id and item.version_id == source.version_id
                for item in body.attachments), 'The greeting must belong to a selected, enabled character version.')
    version = get_version(connection, source.version_id)
    asset = one(connection, 'SELECT kind FROM assets WHERE id=?', (source.asset_id,))
    require(asset['kind'] in {'character', 'persona'} and version['asset_id'] == source.asset_id, 'Choose a character greeting.')
    greetings = version['content'].get('greetings', [])
    require(isinstance(greetings, list), 'This version has no supported greetings. Choose another opening.')
    greeting = next((item for item in greetings if isinstance(item, dict) and item.get('id') == source.greeting_id), None)
    require(greeting is not None and isinstance(greeting.get('text'), str), 'This greeting is unavailable in the selected version.')
    return {'source': 'character_greeting', **source.model_dump(),
            'greeting_modified': body.opening_text != greeting['text'].strip()}


def canonical_kind(kind):
    return 'character' if kind == 'persona' else kind
