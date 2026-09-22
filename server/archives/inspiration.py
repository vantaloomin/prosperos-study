from hashlib import sha256

from server.archives.format import INSPIRATION_TABLES, V53_TABLES
from server.archives.records import related_rows
from server.database import decode, many, one
from server.errors import require
from server.inspiration.models import DeckCreate, Filters
from server.inspiration.pack_content import read_pack
from server.inspiration.selection import eligibility, selected_card
from server.writing.extras import validate_extras


def collect_inspiration(connection, data, complete):
    data['inspiration_draws'] = many(connection, 'SELECT * FROM inspiration_draws ORDER BY rowid') if complete else related_rows(
        connection, 'inspiration_draws', 'branch_id', {row['id'] for row in data['branches']})
    referenced = related_rows(connection, 'inspiration_versions', 'id', {row['version_id'] for row in data['inspiration_draws']})
    data['inspiration_decks'] = many(connection, 'SELECT * FROM inspiration_decks ORDER BY rowid') if complete else related_rows(
        connection, 'inspiration_decks', 'id', {row['deck_id'] for row in referenced})
    data['inspiration_versions'] = related_rows(connection, 'inspiration_versions', 'deck_id', {row['id'] for row in data['inspiration_decks']})
    data['inspiration_pack_origins'] = related_rows(connection, 'inspiration_pack_origins', 'version_id', {row['id'] for row in data['inspiration_versions']})
    data['inspiration_pack_sources'] = related_rows(connection, 'inspiration_pack_sources', 'id', {row['import_id'] for row in data['inspiration_pack_origins']})


def validate_inspiration(connection, data):
    for row in data['inspiration_versions']:
        parsed = DeckCreate(operation_id='archive-validation', name=row['name'], description=row['description'],
                            content=decode(row['content']), note=row['note'], unsupported=decode(row['unsupported']))
        require(parsed.content.model_dump() == decode(row['content']), 'A deck version has invalid or noncanonical card content.')
        validate_extras(parsed.unsupported)
    for row in data['inspiration_decks']:
        head = one(connection, 'SELECT deck_id,number FROM inspiration_versions WHERE id=?', (row['latest_version_id'],))
        maximum = one(connection, 'SELECT MAX(number) AS maximum FROM inspiration_versions WHERE deck_id=?', (row['id'],))
        require(head['deck_id'] == row['id'] and head['number'] == maximum['maximum'], 'A deck head must point to its own latest version.')
    paths = {}
    for row in data['inspiration_draws']:
        validate_draw(connection, row, paths)
    validate_packs(connection, data)


def validate_draw(connection, row, paths):
    deck = one(connection, 'SELECT content FROM inspiration_versions WHERE id=?', (row['version_id'],))
    saved = decode(row['selection'])
    filters = Filters.model_validate(saved['filters']).model_dump()
    calculated = eligibility(decode(deck['content']), filters)
    require(saved == calculated and row['card_id'] == selected_card(calculated, row['ticket']),
            'A recorded draw does not match its deck version, eligibility and ticket.')
    if row['branch_id']:
        branch = one(connection, 'SELECT story_id,head_id FROM branches WHERE id=?', (row['branch_id'],))
        if row['head_id']:
            node = one(connection, 'SELECT story_id FROM nodes WHERE id=?', (row['head_id'],))
            require(node['story_id'] == branch['story_id'], 'A draw source belongs to another Story.')
            if branch['head_id'] not in paths:
                paths[branch['head_id']] = {node['id'] for node in many(connection,
                    'WITH RECURSIVE path AS (SELECT id,parent_id FROM nodes WHERE id=? UNION ALL '
                    'SELECT n.id,n.parent_id FROM nodes n JOIN path p ON p.parent_id=n.id) SELECT id FROM path',
                    (branch['head_id'],))}
            require(row['head_id'] in paths[branch['head_id']], 'A draw source is outside its recorded Story path.')
    else:
        require(row['head_id'] is None, 'A Library draw cannot claim a Story head.')


def validate_packs(connection, data):
    sources = {}
    for row in data['inspiration_pack_sources']:
        raw, _, items = read_pack(row['source_base64'])
        require(sha256(raw).hexdigest() == row['source_sha256'], 'An inspiration pack source hash is invalid.')
        sources[row['id']] = {item['key']: item for item in items}
    for row in data['inspiration_pack_origins']:
        item = sources[row['import_id']][row['item_key']]
        version = one(connection, 'SELECT * FROM inspiration_versions WHERE id=?', (row['version_id'],))
        require(all(version[key] == item[key] for key in ('name', 'description')) and decode(version['content']) == item['content']
                and decode(version['unsupported']) == item['unsupported'] and row['content_sha256'] == item['content_sha256'],
                'A deck import does not match its preserved pack proposal.')


def upgrade_inspiration(document):
    if document['version'] == 53:
        require(set(document['data']) == set(V53_TABLES), 'Version 53 needs its original record groups.')
        document['data'].update({table: [] for table in INSPIRATION_TABLES})
        document['version'] = 54
    return document
