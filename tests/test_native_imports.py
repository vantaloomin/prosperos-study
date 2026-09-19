import base64
import json
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image, PngImagePlugin

from server.archives.validate import parse_archive
from server.errors import DomainError
from server.library_formats.import_conversion import convert_import
from server.library_formats.markdown import read_document
from server.lore.imports import import_candidates, import_entry
from tests.test_archives import backup, restore
from tests.test_library_imports import publish_import, stage

TEXT = 'Aster waits beside the harbor.\r\nThe tide returns. 🌙'
BOOKS = {
    'character-book': {'name': 'Harbor', 'entries': [{'name': 'Tide', 'content': TEXT, 'keys': ['harbor']}]},
    'sillytavern-lorebook': {'name': 'Harbor', 'entries': {'41': {'uid': 41, 'comment': 'Tide', 'content': TEXT,
        'key': ['harbor'], 'keysecondary': ['moon'], 'selective': True, 'selectiveLogic': 3, 'order': 999}}},
    'novelai-lorebook': {'lorebookVersion': 6, 'entries': [{'displayName': 'Tide', 'text': TEXT,
        'keys': ['harbor'], 'searchRange': 2400, 'contextConfig': {'budgetPriority': 999}}]},
    'agnai-lorebook': {'kind': 'memory', 'name': 'Harbor', 'entries': [{'name': 'Tide', 'entry': TEXT,
        'keywords': ['harbor'], 'weight': 999, 'priority': 333}]},
    'risu-lorebook': {'type': 'risu', 'ver': 1, 'data': [
        {'id': 'folder', 'mode': 'folder', 'comment': 'Weather'},
        {'comment': 'Tide', 'content': TEXT, 'key': 'harbor, moon', 'insertorder': 999, 'folder': 'folder'}]},
}


def raw(value):
    return b'\xef\xbb\xbf' + json.dumps(value, ensure_ascii=False, indent=3).encode('utf-8')


@pytest.mark.parametrize('dialect', BOOKS)
def test_native_book_preserves_source_and_proposes_inactive_rules(client, dialect):
    value = {**deepcopy(BOOKS[dialect]), 'unknown': {'script': 'never execute()', 'url': 'https://example.invalid'}}
    source = raw(value)
    preview = stage(client, source, 'harbor.lorebook' if dialect in {'novelai-lorebook', 'risu-lorebook'} else 'harbor.json')
    assert preview['source_format'] == dialect and preview['format'] == 'lorebook-json'
    assert preview['mapping'] and client.get('/api/library').json() == []
    version = publish_import(client, preview).json()['versions'][0]
    assert version['content'] == {'text': ''}  # Entry rules have not become unconditional world knowledge.
    database = client.app.state.database
    candidates = import_candidates(database, version['id'])
    assert len(candidates) == 1 and candidates[0]['title'] == 'Tide'
    proposal = import_entry(database, version['id'], preview['id'], candidates[0]['path'])
    entry = proposal['entry']
    assert entry['text'] == TEXT and not entry['enabled'] and entry['activation'] == 'keywords'
    assert entry['keywords'] == (['harbor', 'moon'] if dialect == 'risu-lorebook' else ['harbor'])
    assert entry['priority'] == 0 and entry['secondary_mode'] == 'none' and entry['minimum_beats'] == 0
    assert 'not translated' in proposal['notice']
    assert client.get(f"/api/library-imports/{preview['id']}/original").content == source
    with ZipFile(BytesIO(client.get(f"/api/library-imports/{preview['id']}/package").content)) as archive:
        assert archive.read('source.json') == source
        metadata, text = read_document(archive.read('converted/' + candidates[0]['path']).decode('utf-8'))
        assert metadata['source_format'] == dialect and text == TEXT
    assert client.get('/api/stories').json() == []


@pytest.mark.parametrize('dialect,keywords,expected', [
    ('agnai-lorebook', ['/literal/'], ['/literal/']),
    ('sillytavern-lorebook', ['harbor', '/moon/i'], []),
    ('novelai-lorebook', ['harbor & moon'], []),
    ('risu-lorebook', 'harbor, /moon/i', []),
])
def test_native_keyword_semantics_are_not_guessed(client, dialect, keywords, expected):
    value = deepcopy(BOOKS[dialect])
    entry = list(value['entries'].values())[0] if dialect == 'sillytavern-lorebook' else (
        value['data'][1] if dialect == 'risu-lorebook' else value['entries'][0])
    key = {'agnai-lorebook': 'keywords', 'novelai-lorebook': 'keys'}.get(dialect, 'key')
    entry[key] = keywords
    preview = stage(client, raw(value), 'book.json')
    version = publish_import(client, preview).json()['versions'][0]
    candidate = import_candidates(client.app.state.database, version['id'])[0]
    proposal = import_entry(client.app.state.database, version['id'], preview['id'], candidate['path'])
    assert proposal['entry']['keywords'] == expected and not proposal['entry']['enabled']
    assert proposal['original_fields'][key] == keywords


@pytest.mark.parametrize('value,expected_name', [
    ({'char_name': 'Aster', 'char_persona': TEXT, 'world_scenario': 'Dusk', 'char_greeting': '{{char}} waits.',
      'example_dialogue': 'Hello.'}, 'Aster'),
    ({'aiName': 'Ast', 'aiDisplayName': 'Aster Vale', 'aiPersona': TEXT, 'scenario': 'Dusk',
      'greeting': '{character} waits.', 'customDialogue': 'Hello.'}, 'Aster Vale'),
])
def test_native_characters_map_once_without_running_macros_or_importing_prompt_overrides(client, value, expected_name):
    value['systemPrompt'] = 'This stays a reference.'
    value['unknown'] = {'nested': [False, None, 'preserve']}
    preview = stage(client, raw(value), 'native.json')
    draft = preview['drafts'][0]
    assert draft['name'] == expected_name and draft['content']['text'] == TEXT
    assert draft['content']['voice'] == '' and draft['content']['example_dialogue'] == 'Hello.'
    assert draft['content']['greetings'][0]['text'] == value.get('char_greeting', value.get('greeting'))
    assert 'systemPrompt' not in draft['content']
    version = publish_import(client, preview).json()['versions'][0]
    archive, _ = backup(client)
    _, mapping = restore(client, archive)
    assert client.get(f"/api/library-imports/{mapping[preview['id']]}/original").content == raw(value)
    assert client.get(f"/api/versions/{mapping[version['id']]}/imports").json()[0]['id'] == mapping[preview['id']]


def test_lorebook_archive_recomputes_mapping_and_rejects_tampered_conversion(client):
    preview = stage(client, raw(BOOKS['novelai-lorebook']), 'Harbor.lorebook')
    publish_import(client, preview)
    archive, document = backup(client)
    _, mapping = restore(client, archive)
    restored = client.get(f"/api/library-imports/{mapping[preview['id']]}").json()
    assert restored['source_format'] == preview['source_format'] and restored['mapping'] == preview['mapping']
    row = document['data']['library_imports'][0]
    converted = json.loads(row['conversion'])
    converted['mapping'][0]['target'] = 'Silently changed mapping'
    row['conversion'] = json.dumps(converted)
    with pytest.raises(DomainError, match='preserved original'):
        parse_archive(json.dumps(document))


@pytest.mark.parametrize('value', [
    {'char_name': 'Aster', 'char_persona': TEXT, 'aiName': 'Other', 'aiPersona': 'Conflicting'},
    {'lorebookVersion': 99, 'entries': []},
    {'type': 'risu', 'ver': 2, 'data': []},
    {'kind': 'memory', 'entries': [{'name': 'Missing prose', 'entry': 42}]},
    {'entries': {'0': {'content': TEXT}, '1': {'content': None}}},
])
def test_bad_or_ambiguous_imports_do_not_stage_or_publish_partial_data(client, value):
    response = client.post('/api/library-imports', json={'filename': 'bad.json',
        'source_base64': base64.b64encode(raw(value)).decode()})
    assert response.status_code == 400
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT count(*) FROM library_imports').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM assets').fetchone()[0] == 0


def test_external_conversion_is_deterministic_and_retains_unknown_metadata():
    source = raw({**BOOKS['agnai-lorebook'], 'metadata': {'custom': [1, False, None]}})
    first = convert_import('Harbor.json', source)
    assert first == convert_import('Harbor.json', source)
    metadata, _ = read_document(first['files']['lorebook/book.md'])
    assert metadata['source_fields']['metadata'] == {'custom': [1, False, None]}


def test_pygmalion_png_retains_portrait_and_native_json(client):
    value = {'char_name': 'Aster', 'char_persona': TEXT, 'char_greeting': 'Welcome.'}
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('chara', base64.b64encode(raw(value)).decode())
    stream = BytesIO()
    Image.new('RGB', (32, 32), 'steelblue').save(stream, format='PNG', pnginfo=metadata)
    source = stream.getvalue()
    preview = stage(client, source, 'Aster.png')
    assert preview['format'] == 'png-card' and preview['source_format'] == 'pygmalion'
    assert preview['drafts'][0]['content']['artwork_sha256'] == preview['source_sha256']
    published = publish_import(client, preview)
    assert published.status_code == 201
    with ZipFile(BytesIO(client.get(f"/api/library-imports/{preview['id']}/package").content)) as archive:
        assert archive.read('source.png') == source and archive.read('source.json') == raw(value)


def test_character_book_and_character_card_are_not_confused():
    from tests.test_card_markdown import card
    value = card()
    converted = convert_import('character.json', raw(value))
    assert converted['format'] == 'card' and converted['card_version'] == 'v3'
    assert [draft['part'] for draft in converted['drafts']] == ['character', 'lorebook']
