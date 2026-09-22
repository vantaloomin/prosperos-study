from secrets import randbelow

from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.inspiration.resources import version
from server.inspiration.selection import eligibility, selected_card
from server.operations import previous, remember


def draw_view(connection, draw_id):
    row = one(connection, 'SELECT * FROM inspiration_draws WHERE id=?', (draw_id,))
    deck = version(connection, row['version_id'])
    card = next(card for card in deck['content']['cards'] if card['id'] == row['card_id'])
    return {**row, 'selection': decode(row['selection']), 'card': card,
            'deck_name': deck['name'], 'deck_number': deck['number'], 'deck_id': deck['deck_id']}


class Draws:
    def __init__(self, database):
        self.database = database

    def view(self, draw_id):
        with self.database.connect() as connection:
            return draw_view(connection, draw_id)

    def history(self, version_id=None, branch_id=None, offset=0):
        with self.database.connect() as connection:
            rows = many(connection, 'SELECT id FROM inspiration_draws WHERE (? IS NULL OR version_id=?) '
                        'AND (? IS NULL OR branch_id=?) ORDER BY created_at DESC,id LIMIT 100 OFFSET ?',
                        (version_id, version_id, branch_id, branch_id, offset))
            return [draw_view(connection, row['id']) for row in rows]

    def create(self, version_id, body):
        payload = {'version_id': version_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'inspiration-draw', payload)
            if saved is not None:
                return saved
            deck = version(connection, version_id)
            require(not deck['archived'], 'This deck is archived. Restore it before drawing.')
            head_id = None
            if body.branch_id:
                branch = one(connection, 'SELECT * FROM branches WHERE id=?', (body.branch_id,))
                require(branch['revision'] == body.expected_revision, 'This Story path changed. Review it before drawing.', 409)
                head_id = branch['head_id']
            selection = eligibility(deck['content'], body.filters.model_dump())
            ticket = randbelow(selection['total_units'])
            identity = identifier()
            connection.execute('INSERT INTO inspiration_draws VALUES (?,?,?,?,?,?,?,?)',
                               (identity, version_id, body.branch_id, head_id, encode(selection), ticket,
                                selected_card(selection, ticket), now()))
            return remember(connection, body.operation_id, 'inspiration-draw', payload, draw_view(connection, identity))
