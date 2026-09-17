import json
from copy import deepcopy
from hashlib import sha256

import pytest

from scripts.convert_character_card import write_package
from server.library_formats.cards import MAX_SOURCE_BYTES, convert_card
from server.library_formats.markdown import document, read_document


def card(version='v3'):
    data = {'name': '../Iona', 'description': '# A quay\r\n\r\nIona waits. 🌧️\n---\n```json\n{}\n```\n',
            'personality': 'Patient.\n\nNot always kind.', 'scenario': '', 'first_mes': '“Come in.”',
            'mes_example': '{{user}}: Hello\n{{char}}: Good evening.',
            'alternate_greetings': ['Rain.', ''], 'group_only_greetings': ['The company arrives.'],
            'system_prompt': 'Do not replace the real system prompt.', 'post_history_instructions': '',
            'creator_notes': 'EDITOR ONLY', 'extensions': {'foreign': {'a': [1, None, False]}},
            'unknown': {'preserve': 'verbatim'}, 'assets': [{'uri': 'https://example.invalid/never-fetch'}],
            'character_book': {'name': 'The harbor', 'description': 'A place between worlds.\n',
                'scan_depth': 12, 'token_budget': 1024, 'recursive_scanning': True, 'extensions': {},
                'entries': [
                    {'id': 7, 'keys': ['quay'], 'secondary_keys': ['rain'], 'selective': True,
                     'content': 'Ships shelter here.\n', 'enabled': True, 'insertion_order': 3,
                     'case_sensitive': True, 'priority': 99, 'position': 'before_char', 'extensions': {}},
                    {'id': 7, 'keys': ['harbor'], 'content': '@@dont_activate\nA secret.\n',
                     'enabled': False, 'insertion_order': 1, 'use_regex': True,
                     'extensions': {'vendor': {'probability': 17}}},
                    {'id': '../../escape', 'keys': [], 'constant': True, 'content': '',
                     'enabled': True, 'insertion_order': 2, 'extensions': {}}]}}
    if version == 'v1':
        return {key: data[key] for key in ('name', 'description', 'personality', 'scenario', 'first_mes', 'mes_example')}
    return {'spec': f'chara_card_{version}', 'spec_version': {'v2': '2.0', 'v3': '3.0'}[version],
            'data': data, 'outside_data': 'Preserve this too.'}


@pytest.mark.parametrize('version', ['v1', 'v2', 'v3'])
def test_programmatic_conversion_preserves_prose_and_exact_original(version, tmp_path):
    value = card(version)
    original = b'\xef\xbb\xbf' + json.dumps(value, ensure_ascii=False, indent=3).encode('utf-8')
    converted = convert_card(original)
    assert converted == convert_card(original)
    assert converted['card_version'] == version and converted['published'] is False
    assert converted['source_sha256'] == sha256(original).hexdigest()
    destination = tmp_path / 'converted'
    write_package(converted, destination)
    assert (destination / 'source.json').read_bytes() == original
    data = value if version == 'v1' else value['data']
    metadata, prose = read_document(converted['files']['character.md'])
    assert prose == data['description']
    assert metadata['source_fields']['name'] == '../Iona'
    assert read_document(converted['files']['character/personality.md'])[1] == data['personality']
    assert read_document(converted['files']['character/example-dialogue.md'])[1] == data['mes_example']
    assert read_document(converted['files']['character/greetings/first.md'])[1] == data['first_mes']
    for path, text in converted['files'].items():
        assert (destination / path).read_bytes() == text.encode('utf-8')
    if version == 'v1':
        assert not any(path.startswith('lorebook/') for path in converted['files'])
    else:
        assert metadata['source_fields']['unknown'] == data['unknown']
        assert metadata['source_fields']['extensions'] == data['extensions']
    assert not (tmp_path / 'escape').exists()


def test_lore_retains_disabled_empty_duplicate_ids_rules_and_source_order():
    value = card()
    files = convert_card(json.dumps(value).encode())['files']
    metadata, prose = read_document(files['lorebook/book.md'])
    assert prose == value['data']['character_book']['description']
    assert metadata['source_fields']['token_budget'] == 1024
    assert metadata['source_fields']['recursive_scanning'] is True
    for index, path in enumerate(metadata['entries']):
        fields, text = read_document(files[path])
        source = value['data']['character_book']['entries'][index]
        assert {**fields['source_fields'], 'content': text} == source
        assert fields['source_index'] == index
    report = convert_card(json.dumps(value).encode())['issues']
    messages = ' '.join(issue['message'] for issue in report)
    assert all(word in messages for word in ('Regex', 'decorators', 'Recursive', 'Extension', 'Macros', 'download'))


@pytest.mark.parametrize('source', [b'[]', b'{"name":"a","name":"b"}', b'{"x":NaN}',
    b'\xff', b'{bad', b'{}', b'{"spec":"chara_card_v4"}',
    b'{"spec":"chara_card_v2","data":[]}', b'[' * 2000 + b']' * 2000,
    b' ' * (MAX_SOURCE_BYTES + 1)], ids=['array', 'duplicate', 'nan', 'encoding', 'syntax',
        'missing-fields', 'unknown-spec', 'bad-data', 'too-deep', 'too-large'])
def test_invalid_sources_fail_without_partial_outputs(source):
    with pytest.raises(ValueError):
        convert_card(source)


@pytest.mark.parametrize('field,value', [('description', None), ('alternate_greetings', [1]),
    ('creator_notes', {}), ('character_book', None), ('character_book', {'entries': [{'content': None}]})])
def test_invalid_supported_fields_require_correction(field, value):
    source = card()
    source['data'][field] = value
    with pytest.raises(ValueError):
        convert_card(json.dumps(source).encode())


def test_publication_is_separate_and_existing_output_is_never_overwritten(tmp_path):
    package = convert_card(json.dumps(card()).encode())
    destination = tmp_path / 'existing'
    destination.mkdir()
    existing = destination / 'keep.md'
    existing.write_text('Do not overwrite me.')
    with pytest.raises(ValueError, match='never overwritten'):
        write_package(package, destination)
    assert existing.read_text() == 'Do not overwrite me.'
    assert list(destination.iterdir()) == [existing]
    invalid = deepcopy(package)
    invalid['files']['../escape.md'] = 'Outside'
    with pytest.raises(ValueError, match='path'):
        write_package(invalid, tmp_path / 'bad-package')
    assert not (tmp_path / 'bad-package').exists()
    assert not (tmp_path / 'escape.md').exists()


def test_plain_markdown_and_structured_source_preserve_arbitrary_prose():
    text = '\n# My world\n\n---\n```\n{}\n```\n\n'
    assert read_document(text) == ({}, text)
    metadata, restored = read_document(document({'kind': 'lorebook', 'title': 'Harbor'}, text))
    assert metadata['kind'] == 'lorebook' and restored == text
    windows_document = document({'kind': 'lorebook'}, 'Keep\r\nthese\r\n').split('\n---\n', 1)
    windows_source = windows_document[0].replace('\n', '\r\n') + '\r\n---\r\n' + windows_document[1]
    assert read_document(windows_source)[1] == 'Keep\r\nthese\r\n'
    with pytest.raises(ValueError, match='version'):
        read_document(document({'kind': 'lorebook'}, text).replace('"format_version": 1', '"format_version": 2'))
    with pytest.raises(ValueError, match='closing'):
        read_document('---\n{"format":"story-library-markdown"}')
