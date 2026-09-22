import json
import re
from hashlib import sha256
from pathlib import PurePosixPath

from server.library_formats.byaf_validation import (
    root_documents,
    text_fields,
    validate_character,
    validate_scenario,
)
from server.library_formats.card_lore import issue
from server.library_formats.container_assets import inspect_asset, propose_artwork
from server.library_formats.containers import member_json, safe_member
from server.library_formats.markdown import document


def byaf_assets(members, character, path, issues):
    result = []
    for asset in character['images']:
        if not isinstance(asset, dict):
            raise ValueError('Each BYAF image needs a relative path and label.')
        text_fields(asset, ('path', 'label'), 'BYAF image')
        safe_member(asset['path'])
        if not re.fullmatch(r'images/[^/]+\.(png|jpe?g|webp|gif)', asset['path']):
            raise ValueError('BYAF image paths must use images/<filename> with a supported declared extension.')
        result.append(inspect_asset(members, str(PurePosixPath(path).parent / asset['path']), asset['label'], 'icon', issues))
    return result


def scenario_fields(character, scenarios):
    first = scenarios[0][1]
    examples = '\n\n'.join(f"{item['characterID']}: {item['text']}" for item in first['exampleMessages'])
    greetings = [item['text'] for _, scenario in scenarios for item in scenario['firstMessages']
                 if item['characterID'] == character['id']]
    return {'scenario': first['narrative'], 'mes_example': examples,
            'first_mes': greetings[0] if greetings else '', 'alternate_greetings': greetings[1:]}


def convert_byaf(source, members):
    from server.library_formats.import_conversion import convert_json

    root, path, scenario_paths = root_documents(members)
    character = member_json(members, path)
    validate_character(character, path)
    scenarios = [(item, member_json(members, item)) for item in scenario_paths]
    for name, value in scenarios:
        validate_scenario(value, name)
    card = {'name': character['displayName'] or character['name'], 'description': character['persona'],
            'personality': '', **scenario_fields(character, scenarios)}
    if character['loreItems']:
        card['character_book'] = {'name': card['name'] + ' · world', 'description': '',
                                  'entries': [{'keys': [item['key']], 'content': item['value'], 'enabled': False}
                                              for item in character['loreItems']]}
    converted = convert_json(json.dumps(card, ensure_ascii=False).encode('utf-8'))
    converted.update(format='byaf', card_version=None, format_label='Backyard Archive Format v1',
                     source_format='byaf-v1', converter_version=3, source_sha256=sha256(source).hexdigest())
    add_reference_documents(converted, root, character, scenarios)
    converted['assets'] = byaf_assets(members, character, path, converted['issues'])
    issue(converted['issues'], 'scenarios', f"{len(scenarios)} scenario(s) preserved. The first listed scenario ({scenario_paths[0]}) supplies the editable scenario and example-dialogue proposal. Its history is reference only; no conversation is accepted into a Story.")
    issue(converted['issues'], 'settings', 'Scenario model settings, formatting instructions, prompt templates, grammar and backgrounds remain reference material. Nothing changes your active configuration or fetches external assets.')
    converted['mapping'] = [
        {'source': 'name, displayName, persona', 'target': 'Character name and background', 'handling': 'mapped'},
        {'source': 'first scenario narrative and examples; character first messages', 'target': 'editable scenario, examples and optional greetings', 'handling': 'review'},
        {'source': 'loreItems', 'target': 'inactive Canon entry proposals', 'handling': 'review'},
        {'source': 'declared images', 'target': 'selectable supported artwork and original downloads', 'handling': 'review'},
        {'source': 'scenario histories, model settings, unknown fields and unlisted files', 'target': 'source documents and original container', 'handling': 'reference'},
    ]
    return propose_artwork(converted)


def add_reference_documents(converted, root, character, scenarios):
    documents = [('manifest', root), ('character', character),
                 *[(f'scenarios/{index + 1:02d}', value) for index, (_, value) in enumerate(scenarios)]]
    for name, value in documents:
        converted['files'][f'byaf/{name}.md'] = document(
            {'kind': 'import-reference', 'source_format': 'byaf-v1'},
            json.dumps(value, ensure_ascii=False, indent=2))
