import threading

from server.archives.format import ArchiveCreate, digest, summary
from server.archives.service import Archives
from server.backups import files, storage
from server.database import many, one
from server.errors import DomainError


class Backups:
    def __init__(self, database):
        self.database = database
        self.review_lock = threading.Lock()
        self.run_lock = threading.Lock()
        storage.initialize(database)

    def settings(self):
        with self.database.connect() as connection:
            row = storage.settings_row(connection)
        return {**row, 'enabled': bool(row['enabled']), 'include_sidebar': bool(row['include_sidebar']),
                'effective_directory': str(files.directory_for(self.database, row))}

    def configure(self, body):
        storage.update(self.database, body)
        return self.settings()

    def history(self):
        return [{**row, 'available': files.availability(row)} for row in storage.history(self.database)]

    def get(self, identity):
        with self.database.connect() as connection:
            return storage.run_view(one(connection, 'SELECT * FROM backup_runs WHERE id=?', (identity,)))

    def run(self, request=None, timestamp=None):
        row, claimed = storage.claim(self.database, lambda settings: files.directory_for(self.database, settings),
                                     request, timestamp)
        if not claimed:
            return row
        with self.run_lock:
            return self.execute(row)

    def execute(self, row):
        try:
            document, content, verification = Archives(self.database).build(
                ArchiveCreate(scope='workspace', include_sidebar=bool(row['settings']['include_sidebar'])))
            files.write_archive(row, content)
            storage.finish(self.database, row['id'], 'ready', sha256=digest(content),
                           byte_count=len(content.encode('utf-8')),
                           summary={**summary(document), 'writer_verification': verification})
        except Exception as error:
            storage.finish(self.database, row['id'], 'error', error=failure_message(error))
            return self.get(row['id'])
        if row['trigger'] == 'scheduled':
            self.prune(row)
        return self.get(row['id'])

    def prune(self, latest):
        with self.database.connect() as connection:
            rows = many(connection, "SELECT * FROM backup_runs WHERE status='ready' AND trigger='scheduled' "
                        'AND directory=? ORDER BY rowid DESC', (latest['directory'],))
        for row in rows[latest['settings']['keep_count']:]:
            try:
                run = storage.run_view(row)
                files.read_archive(run)  # Never delete a changed file or an unowned path.
                files.run_path(run).unlink()
                with self.database.connect(write=True) as connection:
                    connection.execute("UPDATE backup_runs SET status='pruned' WHERE id=?", (row['id'],))
            except Exception:
                with self.database.connect(write=True) as connection:
                    connection.execute('UPDATE backup_runs SET error=? WHERE id=?',
                                       ('The new copy is safe, but an older copy could not be removed. '
                                        'Check the destination and available space.', latest['id']))
                break

    def review(self, identity):
        with self.review_lock:
            run = self.get(identity)
            try:
                content = files.read_archive(run)
            except (OSError, UnicodeError) as error:
                raise DomainError('The saved backup could not be read. Check its destination or choose another copy.', 409) from error
            archives = Archives(self.database)
            if run['archive_id']:
                return archives.review(run['archive_id'])
            staged = archives.stage(content)
            with self.database.connect(write=True) as connection:
                connection.execute('UPDATE backup_runs SET archive_id=? WHERE id=?', (staged['id'], identity))
            return staged


def failure_message(error):
    if isinstance(error, DomainError):
        return error.message
    if isinstance(error, OSError):
        return 'The backup could not be saved. Check that the destination is connected, writable and has free space.'
    return 'The backup could not be completed. Existing saved copies are unchanged. Try again or create a manual archive.'
