from server.branches import insert_node
from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.library_formats.import_conversion import source_bytes
from server.migration.transcript_conversion import convert_transcript
from server.models import StoryCreate
from server.operations import previous, remember
from server.stories import create_story


def validated_transcript(filename, encoded):
    try:
        return convert_transcript(filename, source_bytes(encoded))
    except (ValueError, UnicodeError) as error:
        raise DomainError(str(error), 400) from error


def duplicates(connection, source):
    rows = many(connection, 'SELECT s.id AS story_id,s.title,o.id AS receipt_id,i.id AS import_id,i.source_sha256 '
                'FROM story_imports o JOIN migration_sources i ON i.id=o.import_id JOIN stories s ON s.id=o.story_id '
                'WHERE i.source_sha256=? OR i.content_sha256=? ORDER BY o.created_at,s.id LIMIT 100',
                (source['source_sha256'], source['content_sha256']))
    return [{**row, 'match': 'exact-source' if row['source_sha256'] == source['source_sha256'] else 'message-content'} for row in rows]


def selected_messages(conversion, selections):
    indices = [choice.index for choice in selections]
    require(indices == sorted(set(indices)), 'Select each message once, in its original order.')
    result = []
    for choice in selections:
        require(choice.index < len(conversion['messages']), 'A selected message is missing from this source.')
        message = conversion['messages'][choice.index]
        require(not message['protected'], 'System, developer and tool messages stay reference only.')
        require(choice.variant < len(message['variants']), 'A selected alternative is missing from this message.')
        text = message['variants'][choice.variant]
        require(bool(text.strip()), 'An empty message cannot become Story prose.')
        result.append((choice, message, text))
    return result


def import_metadata(import_id, receipt_id, choice, message):
    return {'source': 'transcript_import', 'import_id': import_id, 'migration_receipt_id': receipt_id,
            'source_index': choice.index, 'variant_index': choice.variant, 'source_role': message['source_role'],
            'speaker': message['speaker'], 'source_timestamp': message['timestamp']}


class TranscriptImports:
    def __init__(self, database):
        self.database = database

    def stage(self, body):
        conversion = validated_transcript(body.filename, body.source_base64)
        row = {'id': identifier(), 'filename': body.filename, 'source_base64': body.source_base64,
               'source_sha256': conversion['source_sha256'], 'content_sha256': conversion['content_sha256'],
               'kind': 'transcript', 'conversion': encode(conversion), 'created_at': now()}
        with self.database.connect(write=True) as connection:
            connection.execute('INSERT INTO migration_sources VALUES (?,?,?,?,?,?,?,?)', tuple(row.values()))
        return self.view(row['id'])

    def row(self, import_id):
        with self.database.connect() as connection:
            return one(connection, 'SELECT * FROM migration_sources WHERE id=?', (import_id,))

    def view(self, import_id):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT * FROM migration_sources WHERE id=?', (import_id,))
            return {**{key: row[key] for key in ('id', 'filename', 'source_sha256', 'content_sha256', 'created_at')},
                    **decode(row['conversion']), 'duplicates': duplicates(connection, row)}

    def list(self):
        with self.database.connect() as connection:
            return many(connection, 'SELECT i.id,i.filename,i.created_at,COUNT(o.id) AS imported_stories '
                        'FROM migration_sources i LEFT JOIN story_imports o ON o.import_id=i.id '
                        "WHERE i.kind='transcript' GROUP BY i.id ORDER BY i.created_at DESC,i.id LIMIT 100")

    def origins(self, story_id):
        with self.database.connect() as connection:
            return [{**row, 'receipt': decode(row['receipt'])} for row in many(connection,
                    'SELECT o.*,i.filename FROM story_imports o JOIN migration_sources i ON i.id=o.import_id WHERE o.story_id=?', (story_id,))]

    def publish(self, import_id, body):
        payload = {'import_id': import_id, **body.model_dump(exclude={'operation_id'})}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'transcript-import', payload)
            if cached is not None:
                return cached
            row = one(connection, 'SELECT * FROM migration_sources WHERE id=?', (import_id,))
            require(row['source_sha256'] == body.source_sha256, 'The source has changed. Reopen its preview.', 409)
            selected = selected_messages(decode(row['conversion']), body.selections)
            matches = duplicates(connection, row)
            if matches and body.duplicate_action == 'skip':
                return remember(connection, body.operation_id, 'transcript-import', payload, {'status': 'skipped', 'duplicates': matches})
            created = create_story(connection, StoryCreate(title=body.title, settings={'experience': 'directed', 'randomness': {'enabled': False}}))
            receipt_id, entries = identifier(), []
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (created['branch_id'],))
            for choice, message, text in selected:
                node_id = insert_node(connection, branch, text, choice.role, import_metadata(import_id, receipt_id, choice, message))
                branch['head_id'] = node_id
                entries.append({**choice.model_dump(), 'node_id': node_id})
            # Import is an explicit bulk acceptance, without scheduling any model maintenance.
            connection.execute('UPDATE branches SET head_id=?,revision=1,updated_at=? WHERE id=?', (branch['head_id'], now(), branch['id']))
            receipt = {'version': 1, 'source_sha256': body.source_sha256, 'title': body.title, 'selections': entries}
            connection.execute('INSERT INTO story_imports VALUES (?,?,?,?,?,?)',
                               (receipt_id, import_id, created['story_id'], created['branch_id'], encode(receipt), now()))
            return remember(connection, body.operation_id, 'transcript-import', payload,
                            {'status': 'imported', **created, 'receipt_id': receipt_id, 'selected_messages': len(entries)})
