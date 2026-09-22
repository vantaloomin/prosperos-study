from collections import Counter
from itertools import takewhile

from server.branch_tools.curation import curation
from server.branch_tools.differences import aligned_rows, row_view
from server.branch_tools.lineage import StorySources
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember


def create_comparison(database, story_id, body):
    payload = {'story_id': story_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        saved = previous(connection, body.operation_id, 'branch-comparison', payload)
        if saved is not None:
            return saved
        branches = {}
        for side in ('left', 'right'):
            row = one(connection, 'SELECT * FROM branches WHERE id=?', (getattr(body, f'{side}_branch_id'),))
            require(row['story_id'] == story_id, 'Compare tellings from the same Story.')
            require(row['revision'] == getattr(body, f'{side}_revision'), 'A telling changed. Refresh before comparing.', 409)
            branches[side] = row
        left, right = branches['left'], branches['right']
        require(left['id'] != right['id'], 'Choose two different tellings.')
        identity = identifier()
        connection.execute('INSERT INTO branch_comparisons VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (identity, story_id, left['id'], right['id'], left['head_id'], right['head_id'],
                            left['revision'], right['revision'], encode({side: row['name'] for side, row in branches.items()}), now()))
        return remember(connection, body.operation_id, 'branch-comparison', payload, {'id': identity})


def comparison_view(connection, row):
    labels = decode(row['labels'])
    return {'id': row['id'], 'story_id': row['story_id'], 'created_at': row['created_at'], **{
        side: {'branch_id': row[f'{side}_branch_id'], 'head_id': row[f'{side}_head_id'],
               'revision': row[f'{side}_revision'], 'name': labels[side],
               'curation': curation(connection, row[f'{side}_branch_id'])} for side in ('left', 'right')}}


def list_comparisons(connection, story_id):
    one(connection, 'SELECT id FROM stories WHERE id=?', (story_id,))
    return [comparison_view(connection, row) for row in many(connection,
            'SELECT * FROM branch_comparisons WHERE story_id=? ORDER BY created_at DESC,id DESC LIMIT 100', (story_id,))]


def read_comparison(connection, identity, offset=0, limit=20, differences_only=False):
    record = one(connection, 'SELECT * FROM branch_comparisons WHERE id=?', (identity,))
    sources = StorySources(connection, record['story_id'])
    left, right = sources.path(record['left_head_id']), sources.path(record['right_head_id'])
    rows = aligned_rows(sources, left, right)
    indices = [row['index'] for row in rows if row['status'] != 'unchanged']
    visible = [row for row in rows if row['index'] >= offset and (not differences_only or row['status'] != 'unchanged')]
    page = visible[:limit]
    shared = list(takewhile(lambda pair: pair[0]['id'] == pair[1]['id'], zip(left, right)))
    common_roots = {sources.original(node['id']) for node in left} & {sources.original(node['id']) for node in right}
    return {**comparison_view(connection, record), 'total': len(rows), 'counts': dict(Counter(row['status'] for row in rows)),
            'difference_indices': indices, 'shared_prefix_count': len(shared),
            'shared_prefix_node_id': shared[-1][0]['id'] if shared else None, 'shared_source_count': len(common_roots),
            'rows': [row_view(sources, row) for row in page],
            'next_offset': visible[limit]['index'] if len(visible) > limit else None}
