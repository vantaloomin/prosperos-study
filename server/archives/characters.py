"""Validate opening provenance without reinterpreting legacy extension fields."""
from server.character_content import opening_metadata
from server.database import decode, one
from server.errors import require
from server.models import StoryCreate


def validate_openings(connection, data):
    for node in data['nodes']:
        metadata = decode(node['metadata'])
        if metadata.get('source') != 'character_greeting':
            continue
        require(node['role'] == 'assistant' and node['parent_id'] is None, 'A greeting must be an opening assistant contribution.')
        manifest = one(connection, 'SELECT attachments FROM manifests WHERE id=?', (node['manifest_id'],))
        body = StoryCreate(title='Archived opening', opening_text=node['text'],
                           opening_source={key: metadata[key] for key in ('asset_id', 'version_id', 'greeting_id')},
                           attachments=decode(manifest['attachments']))
        expected = opening_metadata(connection, body)
        require(type(metadata.get('greeting_modified')) is bool and metadata['greeting_modified'] == expected['greeting_modified'],
                'Greeting adaptation provenance is inconsistent.')
