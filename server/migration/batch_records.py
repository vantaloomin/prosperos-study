from server.database import decode, many, one


def item_row(connection, item_id):
    return one(connection, 'SELECT * FROM migration_batch_items WHERE id=?', (item_id,))


def item_view(row):
    fields = ('id', 'batch_id', 'position', 'filename', 'source_sha256', 'kind', 'import_id', 'status', 'revision', 'error', 'created_at')
    return {key: row[key] for key in fields} | {'candidates': decode(row['candidates']), 'result': decode(row['result'])}


def candidate_matches(first, second):
    result = []
    candidates, others = decode(first['candidates']), decode(second['candidates'])
    for kind, candidate in candidates.items():
        if kind not in others or (first['kind'] and first['kind'] != kind) or (second['kind'] and second['kind'] != kind):
            continue
        proposed = others[kind]['proposals']
        exact = first['source_sha256'] == second['source_sha256']
        parts = [key for key, value in candidate['proposals'].items() if exact or proposed.get(key) == value]
        if parts:
            result.append({'item_id': second['id'], 'filename': second['filename'], 'kind': kind, 'parts': parts,
                           'match': 'exact-source' if exact else 'proposal-content'})
    return result


def batch_view(connection, batch_id):
    batch = one(connection, 'SELECT * FROM migration_batches WHERE id=?', (batch_id,))
    rows = many(connection, 'SELECT * FROM migration_batch_items WHERE batch_id=? ORDER BY position', (batch_id,))
    items = []
    for index, row in enumerate(rows):
        matches = [match for earlier in rows[:index] for match in candidate_matches(row, earlier)]
        prior = native_duplicates(connection, row) if row['kind'] in {'archive', 'writing-bundle'} else []
        items.append({**item_view(row), 'batch_duplicates': matches, 'prior_duplicates': prior})
    return {**batch, 'items': items}


def native_duplicates(connection, row, *, status='complete'):
    # Original native bundle files were not stored by the pre-v0.9 importer.
    # These matches describe migration receipts, not reconstructed name matches.
    rows = many(connection, 'SELECT * FROM migration_batch_items WHERE id<>? AND kind=? AND status=? ORDER BY created_at DESC',
                (row['id'], row['kind'], status))
    return [match for other in rows for match in candidate_matches(row, other)][:100]
