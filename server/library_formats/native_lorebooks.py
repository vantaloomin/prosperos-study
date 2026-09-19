"""Preserve native lorebook entries and expose them to the existing rule review."""
from hashlib import sha256
from pathlib import PureWindowsPath

from server.library_formats.json_formats import text_field
from server.library_formats.markdown import document

CONTENT_FIELDS = {'novelai-lorebook': 'text', 'agnai-lorebook': 'entry'}
KEY_FIELDS = {'sillytavern-lorebook': 'key', 'agnai-lorebook': 'keywords', 'risu-lorebook': 'key'}


def book_entries(value, adapter):
    if adapter.id == 'risu-lorebook':
        if value.get('ver') != 1:
            raise ValueError('This reader supports RisuAI lorebook export version 1.')
        field = 'data'
    else:
        field = 'entries'
    entries = value.get(field)
    expected = dict if adapter.id == 'sillytavern-lorebook' else list
    if not isinstance(entries, expected):
        raise ValueError(f'{adapter.label} must contain a {field} {"object" if expected is dict else "array"}.')
    if len(entries) > 5000:
        raise ValueError('Use at most 5,000 entries per conversion package.')
    if adapter.id == 'novelai-lorebook' and (type(value['lorebookVersion']) is not int or value['lorebookVersion'] not in {3, 4, 5, 6}):
        raise ValueError('This reader supports NovelAI lorebook versions 3 through 6.')
    return list(entries.items()) if expected is dict else list(enumerate(entries))


def entry_documents(rows, adapter):
    files, references = {}, []
    content_field = CONTENT_FIELDS.get(adapter.id, 'content')
    for index, (source_key, entry) in enumerate(rows):
        if not isinstance(entry, dict):
            raise ValueError(f'Lore entry {source_key} must be an object.')
        folder = adapter.id == 'risu-lorebook' and entry.get('mode') == 'folder'
        text = text_field(entry, content_field) if folder else text_field(entry, content_field, None)
        path = f'lorebook/{"folders" if folder else "entries"}/{index + 1:04d}.md'
        files[path] = document({'kind': 'import-reference' if folder else 'lore-entry', 'source_index': index,
                                'source_key': source_key, 'source_format': adapter.id,
                                'source_fields': {key: item for key, item in entry.items() if key != content_field}}, text)
        if not folder:
            references.append(path)
    return files, references


def convert_lorebook(value, source, filename, adapter):
    rows = book_entries(value, adapter)
    files, references = entry_documents(rows, adapter)
    description = text_field(value, 'description')
    name = text_field(value, 'name', PureWindowsPath(filename).stem).strip()[:120] or 'Imported Canon'
    files['lorebook/book.md'] = document({'kind': 'lorebook', 'source_format': adapter.id,
        'source_fields': {key: item for key, item in value.items() if key not in {'entries', 'data', 'description'}},
        'entries': references}, description)
    content_field, key_field = CONTENT_FIELDS.get(adapter.id, 'content'), KEY_FIELDS.get(adapter.id, 'keys')
    return {'converter_version': 1, 'format': 'lorebook-json', 'card_version': None,
            'source_format': adapter.id, 'format_label': adapter.label, 'source_sha256': sha256(source).hexdigest(),
            'files': files, 'status': 'converted-for-review', 'published': False,
            'drafts': [{'part': 'lorebook', 'kind': 'lorebook', 'name': name, 'content': {'text': description}}],
            'mapping': [
                {'source': 'name / description', 'target': 'Canon collection name / overview', 'handling': 'mapped'},
                {'source': content_field, 'target': f'{len(references)} preserved Canon entry texts', 'handling': 'review'},
                {'source': key_field, 'target': 'Plain primary keywords in entry review', 'handling': 'review'},
                {'source': 'Other activation, order, placement, category and extension fields',
                 'target': 'Preserved source fields; no automatic runtime translation', 'handling': 'reference'}],
            'issues': [
                {'path': 'entries', 'message': f'{len(references)} entry texts are preserved separately. Only the edited '
                 'overview below becomes active Canon. After publishing, open Canon entries to add and review imported rules; they start off.'},
                {'path': 'rules', 'message': 'Primary keyword and always-on proposals do not establish equivalent behavior. '
                 'Secondary logic, regex, matching defaults, recursion, timing, probability, placement and ordering need review. '
                 'Foreign priority values are not treated as Prospero priorities.'},
                {'path': 'source', 'message': 'The exact source, folder metadata and unknown fields remain available. '
                 'Macros and scripts remain literal data; import makes no model calls and executes nothing.'}]}
