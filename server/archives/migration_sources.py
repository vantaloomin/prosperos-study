from server.archives.format import MIGRATION_TABLES, V51_TABLES
from server.archives.records import related_rows
from server.database import decode, one
from server.errors import require
from server.migration.models import MessageSelection, TranscriptUpload
from server.migration.transcripts import import_metadata, selected_messages, validated_transcript


def collect_migration_sources(connection, data):
    data['story_imports'] = related_rows(connection, 'story_imports', 'story_id', {row['id'] for row in data['stories']})
    data['migration_sources'] = related_rows(connection, 'migration_sources', 'id', {row['import_id'] for row in data['story_imports']})


def validate_migration_sources(connection, data):
    for row in data['migration_sources']:
        upload = TranscriptUpload(filename=row['filename'], source_base64=row['source_base64'])
        expected = validated_transcript(upload.filename, upload.source_base64)
        require(row['kind'] == 'transcript' and decode(row['conversion']) == expected
                and all(row[key] == expected[key] for key in ('source_sha256', 'content_sha256')),
                'A migrated transcript does not match its preserved original and conversion report.')
    receipts = {row['id']: row for row in data['story_imports']}
    for row in receipts.values():
        validate_receipt(connection, row)
    for node in data['nodes']:
        metadata = decode(node['metadata'])
        if metadata.get('source') == 'transcript_import':
            receipt = receipts.get(metadata.get('migration_receipt_id'))
            require(receipt is not None and receipt['story_id'] == node['story_id'] and receipt['import_id'] == metadata.get('import_id'),
                    'Imported prose is missing its Story source receipt.')


def validate_receipt(connection, row):
    source = one(connection, 'SELECT * FROM migration_sources WHERE id=?', (row['import_id'],))
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
    receipt = decode(row['receipt'])
    require(branch['story_id'] == row['story_id'] and set(receipt) == {'version', 'source_sha256', 'title', 'selections'}
            and receipt['version'] == 1 and receipt['source_sha256'] == source['source_sha256'],
            'A transcript receipt has inconsistent source or Story links.')
    require(isinstance(receipt['title'], str) and 1 <= len(receipt['title']) <= 120
            and isinstance(receipt['selections'], list) and 1 <= len(receipt['selections']) <= 2000,
            'A transcript receipt needs its original title and selected messages.')
    choices = []
    for item in receipt['selections']:
        require(set(item) == {'index', 'variant', 'role', 'node_id'}, 'A transcript receipt has invalid message selections.')
        choices.append(MessageSelection.model_validate({key: value for key, value in item.items() if key != 'node_id'}))
    parent_id = None
    for entry, (choice, message, text) in zip(receipt['selections'], selected_messages(decode(source['conversion']), choices), strict=True):
        node = one(connection, 'SELECT * FROM nodes WHERE id=?', (entry['node_id'],))
        require(node['story_id'] == row['story_id'] and node['parent_id'] == parent_id
                and node['text'] == text and node['role'] == choice.role
                and decode(node['metadata']) == import_metadata(source['id'], row['id'], choice, message),
                'An imported Story message does not match its reviewed source selection.')
        parent_id = node['id']


def remap_receipt(value, mapping):
    return {**value, 'selections': [{**item, 'node_id': mapping[item['node_id']]} for item in value['selections']]}


def upgrade_migration_sources(document):
    if document['version'] == 51:
        require(set(document['data']) == set(V51_TABLES), 'Version 51 needs its original record groups.')
        require(all(decode(row['metadata']).get('source') != 'transcript_import' for row in document['data']['nodes']),
                'Version 51 does not support transcript import provenance.')
        document['data'].update({table: [] for table in MIGRATION_TABLES})
        document['version'] = 52
    return document
