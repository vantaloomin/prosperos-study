from server.authoring.context import authoring_snapshot, defaults, preview_view
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.profiles import profile_snapshot
from server.workflow.context import snapshot_hash
from server.workflow.reviews import job_view


class Authoring:
    def __init__(self, database):
        self.database = database

    def defaults(self, body=None):
        with self.database.connect(write=body is not None) as connection:
            current = defaults(connection)
            if body:
                if body.profile_id:
                    profile_snapshot(connection, body.profile_id)
                    current[body.step] = body.profile_id
                else:
                    current.pop(body.step, None)
                connection.execute("INSERT INTO preferences VALUES ('authoring_profiles',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encode(current),))
            return current

    def preview(self, body):
        with self.database.connect() as connection:
            return preview_view(authoring_snapshot(connection, body))

    def create(self, body):
        payload = body.model_dump()
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'authoring', payload)
            if cached is not None:
                return cached
            snapshot = authoring_snapshot(connection, body)
            require(snapshot_hash(snapshot) == body.preview_hash, 'These inputs or model defaults changed. Preview again.', 409)
            result = insert_run(connection, snapshot)
            return remember(connection, body.operation_id, 'authoring', payload, result)

    def list(self, asset_id=None, offset=0):
        with self.database.connect() as connection:
            condition = ' WHERE asset_id=?' if asset_id else ''
            values = (asset_id,) if asset_id else ()
            return many(connection, 'SELECT id,asset_id,source_version_id,created_at,json_extract(snapshot,\'$.name\') AS name,'
                'json_extract(json_extract(snapshot,\'$.content\'),\'$.target.label\') AS target_label,'
                'json_extract(snapshot,\'$.target_key\') AS target_key,json_extract(snapshot,\'$.step\') AS step FROM authoring_runs'
                + condition + ' ORDER BY rowid DESC LIMIT 100 OFFSET ?', (*values, offset))

    def detail(self, run_id):
        with self.database.connect() as connection:
            run = one(connection, 'SELECT * FROM authoring_runs WHERE id=?', (run_id,))
            jobs = many(connection, 'SELECT * FROM authoring_jobs WHERE run_id=? ORDER BY rowid', (run_id,))
            return {**run, 'snapshot': decode(run['snapshot']), 'jobs': [job_view(job) for job in jobs]}

    def attempts(self, job_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM authoring_jobs WHERE id=?', (job_id,))
            rows = many(connection, 'SELECT * FROM authoring_attempts WHERE job_id=? ORDER BY attempt DESC', (job_id,))
            return [{**row, 'result': decode(row['result']), 'usage': decode(row['usage'])} for row in rows]


def insert_run(connection, snapshot):
    run_id, job_ids = identifier(), []
    jobs = snapshot.pop('jobs')
    connection.execute('INSERT INTO authoring_runs VALUES (?,?,?,?,?)', (run_id, snapshot['asset_id'], snapshot['source_version_id'], encode(snapshot), now()))
    for job in jobs:
        job_id = identifier()
        connection.execute("INSERT INTO authoring_jobs (id,run_id,step,snapshot,status,updated_at) VALUES (?,?,?,?,'queued',?)",
            (job_id, run_id, job['step'], encode(job), now()))
        job_ids.append(job_id)
    return {'id': run_id, 'job_ids': job_ids}
