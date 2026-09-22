from hashlib import sha256

from server.database import encode, identifier, many, now
from server.errors import DomainError, require
from server.library_formats.import_conversion import source_bytes
from server.migration.batch_adapters import preview_item, stage_item
from server.migration.batch_detection import MAX_BATCH_BYTES, inspect_file
from server.migration.batch_records import batch_view, item_row
from server.operations import previous, remember


def inspected_item(body, batch_id, position):
    row = {'id': identifier(), 'batch_id': batch_id, 'position': position, 'filename': body.filename,
           'source_base64': '', 'source_sha256': '', 'candidates': '{}', 'kind': '', 'import_id': None,
           'status': 'rejected', 'revision': 0, 'publication': 'null', 'result': 'null', 'error': '', 'created_at': now()}
    try:
        require(not body.read_error, body.read_error)
        inspection = inspect_file(body)
        candidates = inspection['candidates']
        kind = next(iter(candidates)) if len(candidates) == 1 else ''
        row.update(source_base64=body.source_base64, source_sha256=inspection['source_sha256'], candidates=encode(candidates),
                   kind=kind, status='preparing' if kind else 'choose')
    except (DomainError, ValueError, UnicodeError, TypeError, RecursionError) as error:
        row['error'] = str(error)[:1800]
    return row


def batch_size(files):
    require(sum(len(item.source_base64) for item in files) <= 45 * 1024 * 1024, 'Batch uploads are limited to 32 MiB of original files.')
    total = 0
    for item in files:
        try:
            total += len(source_bytes(item.source_base64))
        except ValueError:
            continue  # Per-file errors remain visible alongside usable files.
    require(total <= MAX_BATCH_BYTES, 'Batch uploads are limited to 32 MiB of original files.')


class MigrationBatches:
    def __init__(self, database):
        self.database = database

    def list(self):
        with self.database.connect() as connection:
            return many(connection, "SELECT b.id,b.created_at,COUNT(i.id) AS items,SUM(i.status IN ('complete','omitted','rejected')) AS finished "
                        'FROM migration_batches b JOIN migration_batch_items i ON i.batch_id=b.id GROUP BY b.id ORDER BY b.created_at DESC LIMIT 100')

    def view(self, batch_id):
        with self.database.connect() as connection:
            return batch_view(connection, batch_id)

    def row(self, item_id):
        with self.database.connect() as connection:
            return item_row(connection, item_id)

    def stage(self, body):
        batch_size(body.files)
        # Operations store only a fingerprint; failed/rejected input bytes do not
        # get copied into an operation receipt or a work queue.
        payload = {'files': [{'filename': item.filename, 'encoded_sha256': sha256(item.source_base64.encode()).hexdigest(), 'read_error': item.read_error} for item in body.files]}
        with self.database.connect() as connection:
            saved = previous(connection, body.operation_id, 'migration-batch-stage', payload)
        if saved is None:
            batch_id = identifier()
            rows = [inspected_item(item, batch_id, index) for index, item in enumerate(body.files)]
            with self.database.connect(write=True) as connection:
                saved = previous(connection, body.operation_id, 'migration-batch-stage', payload)
                if saved is None:
                    connection.execute('INSERT INTO migration_batches VALUES (?,?)', (batch_id, now()))
                    for row in rows:
                        connection.execute('INSERT INTO migration_batch_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
                    saved = remember(connection, body.operation_id, 'migration-batch-stage', payload, {'batch_id': batch_id})
        self.prepare(saved['batch_id'])
        return self.view(saved['batch_id'])

    def prepare(self, batch_id):
        with self.database.connect() as connection:
            rows = many(connection, "SELECT * FROM migration_batch_items WHERE batch_id=? AND status='preparing' ORDER BY position", (batch_id,))
        for row in rows:
            self.prepare_one(row)

    def prepare_one(self, row):
        try:
            import_id = stage_item(self.database, row)
            error, status = '', 'review'
        except (DomainError, OSError, ValueError) as failure:
            import_id, error, status = None, str(failure)[:1800], 'preparation-error'
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE migration_batch_items SET import_id=?,status=?,error=?,revision=revision+1 WHERE id=? AND revision=? AND status='preparing'",
                               (import_id, status, error, row['id'], row['revision']))

    def resolve(self, item_id, body):
        from server.database import decode
        with self.database.connect(write=True) as connection:
            row = item_row(connection, item_id)
            require(row['revision'] == body.expected_revision, 'This batch item changed. Reopen its review.', 409)
            require(row['status'] in {'choose', 'review', 'preparation-error', 'preparing'}, 'This item cannot change interpretation now.', 409)
            require(body.kind in decode(row['candidates']), 'Choose a detected interpretation.')
            connection.execute("UPDATE migration_batch_items SET kind=?,import_id=NULL,status='preparing',error='',revision=revision+1 WHERE id=?", (body.kind, item_id))
            updated = item_row(connection, item_id)
        self.prepare_one(updated)
        return self.view(row['batch_id'])

    def skip(self, item_id, body):
        from server.database import decode
        with self.database.connect(write=True) as connection:
            row = item_row(connection, item_id)
            require(row['revision'] == body.expected_revision, 'This batch item changed. Reopen its review.', 409)
            require(row['status'] in {'review', 'choose', 'omitted', 'rejected'}, 'Finish or retry this item before changing its selection.', 409)
            resumed = 'review' if row['import_id'] else 'choose' if decode(row['candidates']) else 'rejected'
            connection.execute('UPDATE migration_batch_items SET status=?,revision=revision+1 WHERE id=?', ('omitted' if body.skipped else resumed, item_id))
        return self.view(row['batch_id'])

    def preview(self, item_id, mappings=None):
        row = self.row(item_id)
        require(row['status'] in {'review', 'complete', 'publishing'}, 'Choose a valid interpretation before reviewing this item.', 409)
        return preview_item(self.database, row, mappings)
