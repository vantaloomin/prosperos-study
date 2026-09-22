from hashlib import sha256

from server.library_formats.container_assets import charx_assets, propose_artwork
from server.library_formats.containers import member_json


def convert_charx(source, members):
    from server.library_formats.import_conversion import convert_json

    card = member_json(members, 'card.json')
    if card.get('spec') != 'chara_card_v3' or card.get('spec_version') != '3.0':
        raise ValueError('CHARX imports require Character Card V3, specification 3.0.')
    converted = convert_json(members['card.json'])
    converted.update(format='charx', format_label='Character Card V3 container (CHARX)',
                     source_format='charx-v3', converter_version=3, source_sha256=sha256(source).hexdigest())
    converted['assets'] = charx_assets(members, card['data'].get('assets', []), converted['issues'])
    converted['mapping'] = [
        {'source': 'card.json character fields', 'target': 'editable Character and optional Canon proposals', 'handling': 'mapped'},
        {'source': 'embedded image assets', 'target': 'reviewable artwork choices and original downloads', 'handling': 'review'},
        {'source': 'other assets, scripts, external URIs and extensions', 'target': 'preserved original container', 'handling': 'reference'},
    ]
    return propose_artwork(converted)
