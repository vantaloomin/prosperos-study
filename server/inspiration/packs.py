from hashlib import sha256
from pathlib import PureWindowsPath

from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.inspiration.models import DeckCreate
from server.inspiration.pack_content import MAX_PACK_BYTES, content_hash, read_pack
from server.inspiration.resources import create_in, insert_version, version
from server.operations import previous, remember
from server.writing.extras import portable_metadata


def duplicates(connection, item):
    result = []
    for row in connection.execute('SELECT id,deck_id,name,number,content FROM inspiration_versions ORDER BY created_at DESC,id'):
        if content_hash(decode(row['content'])) == item['content_sha256']:
            result.append({key: row[key] for key in ('id', 'deck_id', 'name', 'number')})
        if len(result) == 50:
            break
    return result


def pack_view(connection, import_id):
    row = one(connection, 'SELECT * FROM inspiration_pack_sources WHERE id=?', (import_id,))
    _, pack, items = read_pack(row['source_base64'])
    return {key: row[key] for key in ('id', 'filename', 'source_sha256', 'created_at')} | {
        'name': pack.name, 'description': pack.description,
        'decks': [{**item, 'duplicates': duplicates(connection, item)} for item in items],
        'compatibility': 'Self-contained weighted decks with replacement. All required tags must match exactly. '
                         'Unknown metadata is preserved as reference; foreign actions, dependencies and depletion rules are not enabled.',
        'dependencies': [], 'activation': 'Importing creates Library decks only. It does not draw, enable Story randomness or start model work.'}


class Packs:
    def __init__(self, database):
        self.database = database

    def stage(self, body):
        source, _, _ = read_pack(body.source_base64)
        identity = identifier()
        name = PureWindowsPath(body.filename).name
        require(name and '\x00' not in name, 'Choose a pack with a valid filename.')
        with self.database.connect(write=True) as connection:
            connection.execute('INSERT INTO inspiration_pack_sources VALUES (?,?,?,?,?)',
                               (identity, name, body.source_base64, sha256(source).hexdigest(), now()))
            return pack_view(connection, identity)

    def view(self, import_id):
        with self.database.connect() as connection:
            return pack_view(connection, import_id)

    def original(self, import_id):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT * FROM inspiration_pack_sources WHERE id=?', (import_id,))
        source, _, _ = read_pack(row['source_base64'])
        return row['filename'], source

    def origins(self, version_id):
        with self.database.connect() as connection:
            return many(connection, 'SELECT s.id,s.filename,s.source_sha256,o.item_key FROM inspiration_pack_origins o '
                        'JOIN inspiration_pack_sources s ON s.id=o.import_id WHERE o.version_id=?', (version_id,))

    def publish(self, import_id, body):
        payload = {'import_id': import_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'inspiration-pack-import', payload)
            if saved is not None:
                return saved
            report = pack_view(connection, import_id)
            require(report['source_sha256'] == body.source_sha256, 'The source pack changed. Reopen its review.', 409)
            keys = [choice.key for choice in body.choices]
            require(len(keys) == len(set(keys)) and set(keys) <= {item['key'] for item in report['decks']}, 'Choose each available deck at most once.')
            items = {item['key']: item for item in report['decks']}
            result = {'versions': [], 'skipped': []}
            for choice in body.choices:
                publish_item(connection, import_id, body.operation_id, items[choice.key], choice, result)
            return remember(connection, body.operation_id, 'inspiration-pack-import', payload, result)

    def export(self, body):
        require(len(set(body.version_ids)) == len(body.version_ids), 'Select each deck version once.')
        with self.database.connect() as connection:
            items = [version(connection, version_id) for version_id in body.version_ids]
        document = {'format': 'prospero-inspiration-pack', 'version': 1, 'name': body.name, 'description': body.description,
                    'decks': [{'key': f'deck-{index + 1}', **{key: item[key] for key in ('name', 'description', 'content')},
                               'unsupported': portable_metadata(item['unsupported'])} for index, item in enumerate(items)]}
        require(len(encode(document).encode()) <= MAX_PACK_BYTES, 'This collection exceeds 8 MiB. Select fewer decks or shorten the included card text.')
        return document


def publish_item(connection, import_id, operation_id, item, choice, result):
    require(bool(choice.target_deck_id) == bool(choice.expected_version_id), 'An update needs the exact deck and its current version.')
    matches = duplicates(connection, item)
    if not choice.target_deck_id and choice.duplicate_action == 'skip' and matches:
        result['skipped'].append({'key': item['key'], 'duplicates': matches})
        return
    body = DeckCreate(operation_id=operation_id, **{key: item[key] for key in ('name', 'description', 'content', 'unsupported')})
    if choice.target_deck_id:
        head = one(connection, 'SELECT latest_version_id FROM inspiration_decks WHERE id=?', (choice.target_deck_id,))
        require(head['latest_version_id'] == choice.expected_version_id, 'This deck has a newer version. Reopen the pack review.', 409)
        old = version(connection, choice.expected_version_id)
        created = insert_version(connection, choice.target_deck_id, body, old['number'] + 1)
    else:
        created = create_in(connection, body)
    connection.execute('INSERT INTO inspiration_pack_origins VALUES (?,?,?,?,?)',
                       (created['id'], import_id, item['key'], item['content_sha256'], now()))
    result['versions'].append(created)
