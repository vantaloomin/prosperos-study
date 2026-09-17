"""Deterministic Character Card JSON -> Markdown conversion, without publication."""
from hashlib import sha256

from server.library_formats.card_lore import convert_lore, issue
from server.library_formats.markdown import document, read_json

MAX_SOURCE_BYTES = 10 * 1024 * 1024
BASE_FIELDS = ('name', 'description', 'personality', 'scenario', 'first_mes', 'mes_example')
PROSE_FILES = {'personality': 'character/personality.md', 'scenario': 'character/scenario.md',
               'mes_example': 'character/example-dialogue.md', 'creator_notes': 'character/editor-notes.md',
               'system_prompt': 'character/imported-system-prompt.md',
               'post_history_instructions': 'character/imported-post-history-instructions.md'}


def card_data(value, report):
    if not isinstance(value, dict):
        raise ValueError('A Character Card must be a JSON object.')
    spec = value.get('spec')
    if spec is None:
        return 'v1', value
    if spec not in {'chara_card_v2', 'chara_card_v3'}:
        raise ValueError('Supported card formats are V1, chara_card_v2 and chara_card_v3.')
    data = value.get('data')
    if not isinstance(data, dict):
        raise ValueError('A V2/V3 card must contain a data object.')
    version = 'v2' if spec == 'chara_card_v2' else 'v3'
    if value.get('spec_version') != {'v2': '2.0', 'v3': '3.0'}[version]:
        issue(report, 'spec_version', 'Unexpected specification revision; preserved fields need review.')
    return version, data


def validate_fields(data):
    for field in BASE_FIELDS:
        if not isinstance(data.get(field), str):
            raise ValueError(f'Character Card {field} must be a string (an empty string is allowed).')
    for field in PROSE_FILES:
        if field in data and not isinstance(data[field], str):
            raise ValueError(f'Character Card {field} must be text.')
    for field in ('alternate_greetings', 'group_only_greetings'):
        values = data.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f'{field} must be an array of strings.')
        if len(values) > 5000:
            raise ValueError(f'Use at most 5,000 {field} per conversion package.')


def greeting_files(data):
    files = {'character/greetings/first.md': document(
        {'kind': 'greeting', 'source_field': 'first_mes'}, data['first_mes'])}
    for field in ('alternate_greetings', 'group_only_greetings'):
        for index, text in enumerate(data.get(field, [])):
            path = f'character/greetings/{field}-{index + 1:04d}.md'
            files[path] = document({'kind': 'greeting', 'source_field': field, 'source_index': index}, text)
    return files


def character_files(data):
    files = greeting_files(data)
    for key, path in PROSE_FILES.items():
        if key in data:
            files[path] = document({'kind': 'character-section', 'source_field': key}, data[key])
    excluded = {'description', 'first_mes', 'alternate_greetings', 'group_only_greetings', 'character_book', *PROSE_FILES}
    metadata = {key: value for key, value in data.items() if key not in excluded}
    files['character.md'] = document({'kind': 'character', 'source_fields': metadata,
        'sections': list(files), 'lorebook': 'lorebook/book.md' if 'character_book' in data else None}, data['description'])
    return files


def conversion_issues(data, report):
    if data.get('system_prompt') or data.get('post_history_instructions'):
        issue(report, 'data', 'Imported prompt instructions are separate reference files; they do not replace application prompts.')
    if data.get('assets'):
        issue(report, 'data.assets', 'Asset references are preserved; conversion does not download or execute them.')
    issue(report, 'data', 'Macros remain literal, including random macros. Greetings remain optional authoring material.')


def convert_card(source: bytes) -> dict:
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Character Card JSON must be at most 10 MiB.')
    try:
        value = read_json(source.decode('utf-8-sig'))
    except UnicodeDecodeError as error:
        raise ValueError('Character Card JSON must use UTF-8.') from error
    report = []
    version, data = card_data(value, report)
    validate_fields(data)
    files = character_files(data)
    if 'character_book' in data:
        files.update(convert_lore(data['character_book'], report))
    conversion_issues(data, report)
    return {'converter_version': 1, 'card_version': version, 'source_sha256': sha256(source).hexdigest(),
            'original': source, 'files': files, 'issues': report,
            'status': 'converted-for-review', 'published': False}
