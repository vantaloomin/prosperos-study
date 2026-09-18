"""Store optional plan reviews in the existing durable review queue."""
from server.database import decode, many, one
from server.errors import require
from server.memory.plan_scan import PURPOSE, scan_preview, scan_snapshot
from server.operations import previous, remember
from server.workflow.context import snapshot_hash
from server.workflow.reviews import record_review


class PlanScans:
    def __init__(self, database):
        self.database = database

    def preview(self, branch_id, body):
        with self.database.connect() as connection:
            return scan_preview(scan_snapshot(connection, branch_id, body))

    def create(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'plan-scan', payload)
            if cached is not None:
                return cached
            snapshot = scan_snapshot(connection, branch_id, body)
            require(snapshot_hash(snapshot) == body.preview_hash, 'The passages or configuration changed. Preview this review again.', 409)
            result = record_review(connection, branch_id, snapshot)
            return remember(connection, body.operation_id, 'plan-scan', payload, result)

    def history(self, branch_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
            rows = many(connection, "SELECT id,created_at,snapshot FROM review_runs WHERE branch_id=? "
                        "AND json_extract(snapshot,'$.purpose')=? ORDER BY rowid DESC LIMIT 50", (branch_id, PURPOSE))
            return [{'id': row['id'], 'created_at': row['created_at'],
                     'passages': len(decode(row['snapshot'])['scan_source_ids'])} for row in rows]
