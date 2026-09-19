"""Convert source material into explicit, editable Library publication proposals."""
import base64
import binascii
from hashlib import sha256
from pathlib import PureWindowsPath

from server.library_formats.brain_pack import convert_pack
from server.library_formats.card_lore import issue
from server.library_formats.cards import BASE_FIELDS, MAX_SOURCE_BYTES, convert_card
from server.library_formats.json_formats import external_format
from server.library_formats.markdown import read_document, read_json
from server.library_formats.native_characters import convert_native_character
from server.library_formats.native_lorebooks import convert_lorebook
from server.library_formats.png_cards import embedded_card


def source_bytes(encoded):
    try:
        source = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Choose the original UTF-8 Markdown or JSON file again.') from error
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Library imports are limited to 10 MiB per file.')
    return source


def convert_import(filename, source):
    suffix = PureWindowsPath(filename).suffix.lower()
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Library imports are limited to 10 MiB per file.')
    if suffix in {'.json', '.lorebook'}:
        return convert_json(source, filename)
    if suffix == '.png':
        return convert_png(source)
    if suffix not in {'.md', '.markdown'}:
        raise ValueError('Choose Markdown, supported character JSON / PNG, or a lorebook JSON / .lorebook file.')
    return convert_markdown(filename, source)


def convert_json(source, filename='import.json'):
    value = read_json(source.decode('utf-8-sig'))
    if isinstance(value, dict) and str(value.get('schema', '')).startswith('sgc-brain/'):
        return convert_pack(value, source)
    # Preserve the established CC converter byte-for-byte for historical receipts.
    explicit_card = isinstance(value, dict) and ('spec' in value or all(key in value for key in BASE_FIELDS))
    adapter = None if explicit_card else external_format(value)
    if adapter:
        if adapter.kind == 'lorebook':
            return convert_lorebook(value, source, filename, adapter)
        converted, data = convert_native_character(value, source, adapter)
        converted['drafts'] = card_drafts(data, converted['issues'])
        return converted
    converted = convert_card(source)
    data = value if converted['card_version'] == 'v1' else value['data']
    drafts = card_drafts(data, converted['issues'])
    return {key: value for key, value in converted.items() if key != 'original'} | {'format': 'card', 'drafts': drafts}


def convert_png(source):
    embedded, metadata = embedded_card(source)
    converted = convert_json(embedded)
    if converted['format'] not in {'card', 'native-character'}:
        raise ValueError('PNG metadata must contain a Character Card. Import knowledge packs and lorebooks as JSON files.')
    if metadata['png_payload'] == 'ccv3' and converted['card_version'] != 'v3':
        raise ValueError('The PNG ccv3 payload must contain a V3 Character Card.')
    digest = sha256(source).hexdigest()
    converted.update(metadata, format='png-card', converter_version=2, source_sha256=digest)
    converted['drafts'][0]['content']['artwork_sha256'] = digest
    issue(converted['issues'], 'artwork', 'The image is proposed as artwork. The exact original PNG and extracted JSON are preserved; previews use a still frame and do not send image data to the writer.')
    if metadata['png_legacy_copy']:
        issue(converted['issues'], 'png_payload', 'This PNG also contains a legacy card copy. The V3 payload is used; both remain in the original PNG.')
    return converted


def convert_markdown(filename, source):
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Library imports are limited to 10 MiB per file.')
    metadata, prose = read_document(source.decode('utf-8-sig'))
    if metadata.get('kind') not in {None, 'lorebook', 'lore-entry'}:
        raise ValueError('For characters, choose the original Character Card JSON. This Markdown importer creates lorebooks.')
    name = PureWindowsPath(filename).stem
    fields = metadata.get('source_fields', {})
    if isinstance(fields, dict) and isinstance(fields.get('name'), str):
        name = fields['name']
    issues = []
    if metadata:
        issue(issues, 'metadata', 'Metadata and referenced entry paths are preserved as source material. Only the reviewed prose becomes world knowledge; this single-file import does not load companion files or activate rules.')
    elif prose.startswith('---'):
        issue(issues, 'markdown', 'Only Story Library JSON front matter is parsed. Other front matter remains ordinary prose; review it before publishing.')
    return {'converter_version': 1, 'format': 'markdown', 'card_version': None,
            'source_sha256': sha256(source).hexdigest(), 'files': {'book.md': source.decode('utf-8')},
            'issues': issues, 'status': 'converted-for-review', 'published': False,
            'drafts': [{'part': 'lorebook', 'kind': 'lorebook', 'name': name[:120] or 'Imported world', 'content': {'text': prose}}]}


def mapped_greetings(data, issues):
    values = [('first_mes', data['first_mes'])] + [
        (f'alternate_greetings[{index}]', text) for index, text in enumerate(data.get('alternate_greetings', []))]
    usable = [(field, text) for field, text in values if text.strip() and len(text) <= 100000]
    if len(usable) != len(values) or len(usable) > 32 or data.get('group_only_greetings'):
        issue(issues, 'greetings', 'Up to 32 nonempty, supported individual greetings are proposed below. Empty, oversized, extra and group-only greetings remain in the original and converted Markdown files.')
    return [{'id': field, 'label': 'Original opening' if field == 'first_mes' else f'Alternative {index}', 'text': text}
            for index, (field, text) in enumerate(usable[:32])]


def card_drafts(data, issues):
    content = {'text': data['description'], 'voice': data['personality'], 'scenario': data['scenario'],
               'example_dialogue': data['mes_example'], 'author_notes': data.get('creator_notes', ''),
               'greetings': mapped_greetings(data, issues)}
    drafts = [{'part': 'character', 'kind': 'character', 'name': data['name'][:120] or 'Imported character', 'content': content}]
    if 'character_book' in data:
        book = data['character_book']
        name = book.get('name') if isinstance(book.get('name'), str) else f"{data['name']} · world"
        drafts.append({'part': 'lorebook', 'kind': 'lorebook', 'name': name[:120] or 'Imported world',
                       'content': {'text': book.get('description', '')}})
        issue(issues, 'lorebook.entries', f"All {len(book['entries'])} entries are preserved as Markdown reference files. They remain inactive until their rules are mapped; only the editable book overview below becomes world knowledge. Selecting both items links the character to this book.")
    return drafts
