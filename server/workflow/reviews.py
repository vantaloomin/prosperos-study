from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.scenes.reviews import scene_review_current, scene_review_snapshot
from server.workflow.context import preview_view, review_snapshot, snapshot_hash


def prepare_snapshot(connection, branch_id, body):
    builder = scene_review_snapshot if body.scene_id is not None else review_snapshot
    return builder(connection, branch_id, body)


def job_view(row):
    snapshot = decode(row["snapshot"])
    snapshot["profile"].pop("credential_ref", None)
    return {**row, "snapshot": snapshot, "result": decode(row["result"]), "usage": decode(row["usage"])}


class Reviews:
    def __init__(self, database):
        self.database = database

    def preview(self, branch_id, body):
        with self.database.connect() as connection:
            return preview_view(prepare_snapshot(connection, branch_id, body))

    def create(self, branch_id, body):
        payload = {"branch_id": branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "review", payload)
            if cached is not None:
                return cached
            snapshot = prepare_snapshot(connection, branch_id, body)
            require(body.preview_hash == snapshot_hash(snapshot), "The review inputs changed. Preview the requests again.", 409)
            result = record_review(connection, branch_id, snapshot)
            return remember(connection, body.operation_id, "review", payload, result)

    def detail(self, run_id):
        with self.database.connect() as connection:
            run = one(connection, "SELECT * FROM review_runs WHERE id=?", (run_id,))
            snapshot = decode(run["snapshot"])
            return {**run, "snapshot": snapshot, "selections": decode(run["selections"]),
                    "current_scene_draft": scene_review_current(connection, snapshot),
                    "jobs": [job_view(row) for row in many(connection, "SELECT * FROM review_jobs WHERE run_id=? ORDER BY rowid", (run_id,))]}

    def list(self, branch_id, scene_id=None):
        with self.database.connect() as connection:
            one(connection, "SELECT id FROM branches WHERE id=?", (branch_id,))
            condition = " AND json_extract(snapshot,'$.scene.id')=?" if scene_id is not None else ""
            values = (branch_id, scene_id) if scene_id is not None else (branch_id,)
            rows = many(connection, "SELECT id,created_at,json_extract(snapshot,'$.scene.id') AS scene_id,"
                        "json_extract(snapshot,'$.scene.title') AS scene_title FROM review_runs WHERE branch_id=?"
                        + " AND COALESCE(json_extract(snapshot,'$.purpose'),'') != 'planned-continuity-v1'"
                        + condition + " ORDER BY created_at DESC", values)
            return [{"id": row["id"], "created_at": row["created_at"],
                     "scene": {"id": row["scene_id"], "title": row["scene_title"]} if row["scene_id"] else None} for row in rows]

    def select(self, run_id, job_id):
        with self.database.connect(write=True) as connection:
            run = one(connection, "SELECT * FROM review_runs WHERE id=?", (run_id,))
            job = one(connection, "SELECT * FROM review_jobs WHERE id=?", (job_id,))
            require(job["run_id"] == run_id and job["status"] == "done", "Select a completed result from this review.", 409)
            selections = {**decode(run["selections"]), job["step"]: job_id}
            connection.execute("UPDATE review_runs SET selections=? WHERE id=?", (encode(selections), run_id))
            return {"selections": selections}

    def attempts(self, job_id):
        with self.database.connect() as connection:
            rows = many(connection, "SELECT * FROM review_attempts WHERE job_id=? ORDER BY attempt DESC", (job_id,))
            return [{**row, "result": decode(row["result"]), "usage": decode(row["usage"])} for row in rows]


def record_review(connection, branch_id, snapshot):
    run_id = identifier()
    jobs = snapshot.pop('jobs')
    connection.execute('INSERT INTO review_runs (id,branch_id,snapshot,created_at) VALUES (?,?,?,?)',
                       (run_id, branch_id, encode(snapshot), now()))
    job_ids = []
    for job in jobs:
        job_id = identifier()
        connection.execute("INSERT INTO review_jobs (id,run_id,step,snapshot,status,updated_at) VALUES (?,?,?,?,'queued',?)",
                           (job_id, run_id, job['step'], encode(job), now()))
        job_ids.append(job_id)
    return {'id': run_id, 'job_ids': job_ids}
