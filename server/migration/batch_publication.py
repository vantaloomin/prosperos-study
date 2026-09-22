from server.database import decode, encode
from server.errors import DomainError, require
from server.migration.batch_adapters import publish_item, saved_publication
from server.migration.batch_records import item_row, item_view, native_duplicates


def publication_choices(body):
    choices = {key: value for key, value in body.choices.items() if key != 'operation_id'}
    require(len(encode(choices).encode()) <= 2 * 1024 * 1024, 'One reviewed item is limited to 2 MiB of choices.')
    return choices


def claim_publication(database, item_id, choices, expected_revision):
    with database.connect(write=True) as connection:
        row = item_row(connection, item_id)
        if row['status'] in {'publishing', 'complete'}:
            require(decode(row['publication']) == choices, 'This item already has a saved publication. Retry those saved choices.', 409)
            return row
        require(row['status'] == 'review', 'Review a prepared item before importing it.', 409)
        require(row['revision'] == expected_revision, 'This item changed. Reopen its review before importing.', 409)
        if row['kind'] in {'archive', 'writing-bundle'}:
            require(not native_duplicates(connection, row, status='publishing'), 'A matching native item is being imported. Finish or retry that item first.', 409)
        connection.execute("UPDATE migration_batch_items SET status='publishing',publication=?,error='',revision=revision+1 WHERE id=?", (encode(choices), item_id))
        return item_row(connection, item_id)


def execute_publication(database, row, choices):
    saved = saved_publication(database, row, choices)
    if saved is not None:
        return saved
    if row['kind'] not in {'archive', 'writing-bundle'}:
        return publish_item(database, row, choices)
    choices = dict(choices)
    decision = choices.pop('duplicate_action', 'skip')
    require(decision in {'skip', 'new'}, 'Choose skip or a deliberate new copy for duplicate native material.')
    with database.connect() as connection:
        matches = native_duplicates(connection, row)
    if matches and decision == 'skip':
        return {'status': 'skipped', 'duplicates': matches}
    return publish_item(database, row, choices)


def complete_publication(database, row, choices):
    if row['status'] == 'complete':
        return item_view(row)
    try:
        result = execute_publication(database, row, choices)
    except DomainError as error:
        with database.connect(write=True) as connection:
            connection.execute("UPDATE migration_batch_items SET status='review',publication='null',error=?,revision=revision+1 WHERE id=? AND status='publishing'",
                               (error.message, row['id']))
        raise
    except Exception:
        with database.connect(write=True) as connection:
            connection.execute("UPDATE migration_batch_items SET error=? WHERE id=? AND status='publishing'",
                               ('Publication was interrupted. Retry the saved choices to recover its recorded result.', row['id']))
        raise DomainError('Publication was interrupted. Retry the saved choices; this cannot duplicate a successful import.', 503) from None
    with database.connect(write=True) as connection:
        connection.execute("UPDATE migration_batch_items SET status='complete',result=?,error='',revision=revision+1 WHERE id=? AND status='publishing'",
                           (encode(result), row['id']))
        return item_view(item_row(connection, row['id']))


def publish_batch_item(database, item_id, body):
    choices = publication_choices(body)
    row = claim_publication(database, item_id, choices, body.expected_revision)
    return complete_publication(database, row, choices)


def retry_batch_item(database, item_id, body):
    with database.connect() as connection:
        row = item_row(connection, item_id)
    require(row['status'] in {'publishing', 'complete'}, 'There is no interrupted publication to retry.', 409)
    require(row['revision'] == body.expected_revision, 'This item changed. Reload its saved result.', 409)
    return complete_publication(database, row, decode(row['publication']))
