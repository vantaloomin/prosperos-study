from datetime import UTC, datetime, timedelta

from server.database import decode, encode, identifier, many, now, one
from server.errors import require


def next_due(timestamp, interval):
    return (datetime.fromisoformat(timestamp) + timedelta(minutes=interval)).isoformat()


def initialize(database):
    with database.connect(write=True) as connection:
        connection.execute('INSERT OR IGNORE INTO backup_settings '
                           '(id,workspace_id,updated_at) VALUES (1,?,?)', (identifier(), now()))


def settings_row(connection):
    return one(connection, 'SELECT * FROM backup_settings WHERE id=1')


def run_view(row):
    return {**row, 'settings': decode(row['settings']), 'summary': decode(row['summary'])}


def history(database):
    with database.connect() as connection:
        rows = many(connection, 'SELECT * FROM backup_runs ORDER BY rowid DESC LIMIT 100')
    return [run_view(row) for row in rows]


def update(database, body):
    timestamp = now()
    with database.connect(write=True) as connection:
        current = settings_row(connection)
        require(current['revision'] == body.expected_revision,
                'Backup settings changed elsewhere. Reload them before saving.', 409)
        connection.execute('UPDATE backup_settings SET enabled=?,interval_minutes=?,keep_count=?,'
                           'destination=?,include_sidebar=?,next_run_at=?,updated_at=?,revision=revision+1 WHERE id=1',
                           (body.enabled, body.interval_minutes, body.keep_count, body.destination,
                            body.include_sidebar, next_due(timestamp, body.interval_minutes) if body.enabled else None,
                            timestamp))


def claim(database, directory_for, request=None, timestamp=None):
    timestamp = timestamp or datetime.now(UTC).isoformat()
    with database.connect(write=True) as connection:
        settings = settings_row(connection)
        cached = existing_request(connection, request, settings)
        if cached:
            return cached, False
        if not request and (not settings['enabled'] or settings['next_run_at'] > timestamp):
            return None, False
        running = connection.execute("SELECT id FROM backup_runs WHERE status='running'").fetchone()
        if running:
            require(request is None, 'A backup is already being prepared. Wait for it to finish.', 409)
            return None, False
        run_id = identifier()
        connection.execute('INSERT INTO backup_runs '
                           '(id,operation_id,trigger,status,settings,directory,started_at) VALUES (?,?,?,?,?,?,?)',
                           (run_id, request.operation_id if request else None, 'manual' if request else 'scheduled',
                            'running', encode(settings), str(directory_for(settings)), timestamp))
        if not request:
            connection.execute('UPDATE backup_settings SET next_run_at=? WHERE id=1',
                               (next_due(timestamp, settings['interval_minutes']),))
        return run_view(one(connection, 'SELECT * FROM backup_runs WHERE id=?', (run_id,))), True


def existing_request(connection, request, settings):
    if request is None:
        return None
    row = connection.execute('SELECT * FROM backup_runs WHERE operation_id=?', (request.operation_id,)).fetchone()
    if row:
        cached = run_view(dict(row))
        require(cached['settings']['revision'] == request.expected_revision,
                'This backup request identifier was already used with different settings.', 409)
        return cached
    require(settings['revision'] == request.expected_revision,
            'Backup settings changed. Reload them before creating a copy.', 409)
    return None


def finish(database, run_id, status, *, error='', sha256='', byte_count=0, summary=None):
    with database.connect(write=True) as connection:
        connection.execute('UPDATE backup_runs SET status=?,finished_at=?,error=?,sha256=?,byte_count=?,summary=? WHERE id=?',
                           (status, now(), error, sha256, byte_count, encode(summary or {}), run_id))


def recover(database):
    with database.connect(write=True) as connection:
        connection.execute("UPDATE backup_runs SET status='interrupted',finished_at=?,error=? WHERE status='running'",
                           (now(), 'The app stopped before this backup was recorded as complete. Create another copy.'))
