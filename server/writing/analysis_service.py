from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.workflow.context import snapshot_hash
from server.workflow.reviews import job_view
from server.writing.analysis_context import analysis_snapshot, preview_view


class StyleAnalyses:
    def __init__(self, database):
        self.database = database

    def preview(self, body):
        with self.database.connect() as connection:
            return preview_view(analysis_snapshot(connection, body))

    def create(self, body):
        with self.database.connect(write=True) as connection:
            payload = body.model_dump()
            saved = previous(connection, body.operation_id, 'style-analysis', payload)
            if saved is not None:
                return saved
            snapshot = analysis_snapshot(connection, body)
            require(snapshot_hash(snapshot) == body.preview_hash, 'The selected samples or model instructions changed. Preview again.', 409)
            job_id = identifier()
            connection.execute('INSERT INTO style_analysis_jobs (id,source_version_id,draft_id,step,snapshot,status,updated_at) '
                               "VALUES (?,?,?,?,?,'queued',?)", (job_id, body.source_version_id, body.draft_id, 'library-assist', encode(snapshot), now()))
            return remember(connection, body.operation_id, 'style-analysis', payload, {'id': job_id})

    def detail(self, job_id):
        with self.database.connect() as connection:
            return job_view(one(connection, 'SELECT * FROM style_analysis_jobs WHERE id=?', (job_id,)))

    def operation(self, operation_id):
        with self.database.connect() as connection:
            row = connection.execute("SELECT result FROM operations WHERE id=? AND kind='style-analysis'", (operation_id,)).fetchone()
            return decode(row['result']) if row else None

    def list(self, source_version_id=None, draft_id=None):
        with self.database.connect() as connection:
            return many(connection, 'SELECT id,source_version_id,draft_id,status,updated_at,json_extract(snapshot,\'$.name\') AS name '
                        'FROM style_analysis_jobs WHERE (? IS NULL OR source_version_id=?) AND (? IS NULL OR draft_id=?) ORDER BY rowid DESC LIMIT 100',
                        (source_version_id, source_version_id, draft_id, draft_id))

    def attempts(self, job_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM style_analysis_jobs WHERE id=?', (job_id,))
            return [{**row, 'result': decode(row['result']), 'usage': decode(row['usage'])} for row in many(
                connection, 'SELECT * FROM style_analysis_attempts WHERE job_id=? ORDER BY attempt', (job_id,))]
