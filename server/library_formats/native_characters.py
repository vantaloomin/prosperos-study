"""Native character fields mapped once into Prospero's authoring fields."""
from hashlib import sha256

from server.database import encode
from server.library_formats.cards import convert_card
from server.library_formats.json_formats import text_field
from server.library_formats.markdown import document

FIELD_MAPS = {
    'pygmalion': {'name': 'char_name', 'description': 'char_persona', 'scenario': 'world_scenario',
                  'first_mes': 'char_greeting', 'mes_example': 'example_dialogue'},
    'backyard-legacy': {'name': 'aiName', 'description': 'aiPersona', 'scenario': 'scenario',
                        'first_mes': 'firstMessage', 'mes_example': 'customDialogue',
                        'personality': 'personality'},
}
TARGETS = {'name': 'Character name', 'description': 'Character & background', 'personality': 'Voice',
           'scenario': 'Scenario', 'first_mes': 'Optional opening greeting', 'mes_example': 'Example dialogue'}


def source_fields(value, adapter):
    fields = FIELD_MAPS[adapter.id].copy()
    if adapter.id == 'backyard-legacy':
        aliases = {'name': ('aiDisplayName', 'aiName'), 'first_mes': ('firstMessage', 'greeting', 'first_mes'),
                   'mes_example': ('customDialogue', 'examples', 'mes_example')}
        for target, names in aliases.items():
            fields[target] = next((name for name in names if name in value), fields[target])
    return fields


def convert_native_character(value, source, adapter):
    fields = source_fields(value, adapter)
    data = {key: text_field(value, fields[key]) if key in fields else '' for key in TARGETS}
    # A single persona blob belongs in background once; duplicating it into voice
    # would repeat the same instructions in every writer request.
    converted = convert_card(encode(data).encode('utf-8'))
    converted.pop('original')
    converted['files']['character/native-fields.md'] = document(
        {'kind': 'import-reference', 'source_format': adapter.id, 'source_fields': value}, '')
    converted.update(format='native-character', card_version=None, converter_version=1,
                     source_sha256=sha256(source).hexdigest(), source_format=adapter.id, format_label=adapter.label)
    converted['mapping'] = [{'source': source_key, 'target': TARGETS[key], 'handling': 'mapped'}
                            for key, source_key in fields.items() if source_key in value]
    converted['mapping'].append({'source': 'Other source fields', 'target': 'Preserved original and native-fields.md',
                                 'handling': 'reference'})
    converted['issues'].append({'path': 'native_fields', 'message':
        'Only the listed character fields are proposed. Other fields, including model settings, prompt overrides, '
        'scripts and media references, remain in the preserved source. Nothing is downloaded or executed.'})
    return converted, data
