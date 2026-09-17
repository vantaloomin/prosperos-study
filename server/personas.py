"""Reusable viewpoint identity, separate from permission to control the character."""
from server.errors import require

FIELDS = {'text': 100000, 'address': 1000, 'pronouns': 300, 'author_notes': 100000}
USAGE = ('This persona describes the author\'s viewpoint identity, not an additional NPC. '
         'Story participation notes add local direction. A persona never grants permission '
         'to control the character; follow the Story\'s player_agency setting.')


def validate_persona(content):
    require(set(content) <= set(FIELDS) | {'artwork_sha256'}, 'Personas support description, form of address, pronouns, artwork and editor notes.')
    for key, value in content.items():
        if key == 'artwork_sha256':
            continue
        require(isinstance(value, str) and len(value) <= FIELDS[key],
                f'Persona {key} must be text of at most {FIELDS[key]:,} characters.')


def persona_context(content):
    return {'usage': USAGE, **{key: value for key, value in content.items() if key not in {'author_notes', 'artwork_sha256'}}}


def validate_persona_selection(connection, attachments):
    ids = [item['asset_id'] for item in attachments if item['enabled']]
    if not ids:
        return
    placeholders = ','.join('?' for _ in ids)
    count = connection.execute(f"SELECT COUNT(*) FROM assets WHERE kind='persona' AND id IN ({placeholders})", ids).fetchone()[0]
    require(count <= 1, 'Choose at most one active viewpoint persona for a Story.')
