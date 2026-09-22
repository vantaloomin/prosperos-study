from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.writing.extras import validate_extras


def version(connection, version_id):
    row = one(connection, 'SELECT v.*,d.archived,d.revision FROM inspiration_versions v '
              'JOIN inspiration_decks d ON d.id=v.deck_id WHERE v.id=?', (version_id,))
    return {**row, 'content': decode(row['content']), 'unsupported': decode(row['unsupported'])}


def insert_version(connection, deck_id, body, number):
    identity = identifier()
    extras = validate_extras(body.unsupported)
    connection.execute('INSERT INTO inspiration_versions VALUES (?,?,?,?,?,?,?,?,?)',
                       (identity, deck_id, number, body.name, body.description, encode(body.content.model_dump()),
                        encode(extras), body.note, now()))
    connection.execute('UPDATE inspiration_decks SET latest_version_id=? WHERE id=?', (identity, deck_id))
    return version(connection, identity)


def create_in(connection, body):
    identity = identifier()
    connection.execute('INSERT INTO inspiration_decks VALUES (?,NULL,0,0,?)', (identity, now()))
    return insert_version(connection, identity, body, 1)


class Decks:
    def __init__(self, database):
        self.database = database

    def list(self, include_archived=False):
        with self.database.connect() as connection:
            return [version(connection, row['latest_version_id']) for row in many(connection,
                    'SELECT latest_version_id FROM inspiration_decks WHERE archived=0 OR ? ORDER BY created_at,id', (include_archived,))]

    def version(self, version_id):
        with self.database.connect() as connection:
            return version(connection, version_id)

    def history(self, deck_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM inspiration_decks WHERE id=?', (deck_id,))
            return [version(connection, row['id']) for row in many(connection,
                    'SELECT id FROM inspiration_versions WHERE deck_id=? ORDER BY number DESC', (deck_id,))]

    def create(self, body):
        payload = body.model_dump()
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'deck-create', payload)
            if saved is not None:
                return saved
            return remember(connection, body.operation_id, 'deck-create', payload, create_in(connection, body))

    def publish(self, deck_id, body):
        payload = {'deck_id': deck_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'deck-publish', payload)
            if saved is not None:
                return saved
            current = one(connection, 'SELECT * FROM inspiration_decks WHERE id=?', (deck_id,))
            require(current['latest_version_id'] == body.expected_version_id, 'This deck has a newer version. Reopen it before publishing.', 409)
            old = version(connection, current['latest_version_id'])
            if 'unsupported' not in body.model_fields_set:
                body = body.model_copy(update={'unsupported': old['unsupported']})
            result = insert_version(connection, deck_id, body, old['number'] + 1)
            return remember(connection, body.operation_id, 'deck-publish', payload, result)

    def archive(self, deck_id, body):
        payload = {'deck_id': deck_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'deck-archive', payload)
            if saved is not None:
                return saved
            deck = one(connection, 'SELECT * FROM inspiration_decks WHERE id=?', (deck_id,))
            require(deck['revision'] == body.expected_revision, 'This deck changed. Refresh before archiving.', 409)
            connection.execute('UPDATE inspiration_decks SET archived=?,revision=revision+1 WHERE id=?', (body.archived, deck_id))
            return remember(connection, body.operation_id, 'deck-archive', payload, version(connection, deck['latest_version_id']))
