from server.agent_switches import require_agent
from server.database import many, now, one
from server.errors import require
from server.memory.maintenance_intents import automatic_policy
from server.memory.maintenance_models import BackfillPreview
from server.memory.maintenance_planning import batch_plan, batch_preview, guard_batch
from server.memory.maintenance_storage import batch_detail, insert_batch
from server.operations import previous, remember
from server.workflow.context import snapshot_hash


class Maintenance:
    def __init__(self, database):
        self.database = database

    def preview(self, branch_id, body):
        with self.database.connect() as connection:
            return batch_preview(batch_plan(connection, branch_id, body))

    def create(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect() as connection:
            cached = previous(connection, body.operation_id, 'summary-backfill', payload)
            if cached is not None:
                return cached
            plan = batch_plan(connection, branch_id, body)
            require(snapshot_hash(plan) == body.preview_hash, 'Sources or model settings changed. Preview backfill again.', 409)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'summary-backfill', payload)
            if cached is not None:
                return cached
            guard_batch(connection, plan, body)
            return remember(connection, body.operation_id, 'summary-backfill', payload, insert_batch(connection, plan, 'backfill'))

    def status(self, branch_id):
        with self.database.connect() as connection:
            policy, active = automatic_policy(connection, branch_id)
            wakeups = many(connection, 'SELECT * FROM summary_wakeups WHERE branch_id=?', (branch_id,))
            pending = one(connection, 'SELECT COUNT(*) AS count FROM summary_pending WHERE branch_id=?', (branch_id,))['count']
            return {'settings': policy.model_dump(), 'active': active, 'wakeup': wakeups[0] if wakeups else None,
                    'waiting_contributions': pending}

    def history(self, branch_id, offset=0):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
            return many(connection, 'SELECT id,kind,status,error,created_at FROM summary_batches WHERE branch_id=? '
                        'ORDER BY rowid DESC LIMIT 25 OFFSET ?', (branch_id, offset))

    def detail(self, batch_id):
        with self.database.connect() as connection:
            return batch_detail(connection, batch_id)

    def resume_waiting(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'summary-waiting', payload)
            if cached is not None:
                return cached
            policy, active = automatic_policy(connection, branch_id)
            require(active, 'Enable automatic summaries and its prompt before resuming.', 409)
            row = one(connection, 'SELECT * FROM summary_wakeups WHERE branch_id=?', (branch_id,))
            require(row['revision'] == body.expected_revision and row['status'] in {'limited', 'paused', 'error', 'interrupted'},
                    'The maintenance queue changed. Refresh its status before resuming.', 409)
            connection.execute("UPDATE summary_wakeups SET revision=revision+1,status='pending',error='',allowance=?,updated_at=? WHERE id=?",
                               (policy.max_batches, now(), row['id']))
            return remember(connection, body.operation_id, 'summary-waiting', payload, {'resumed': True})


def automatic_plan(database, branch_id):
    with database.connect() as connection:
        wake = one(connection, 'SELECT * FROM summary_wakeups WHERE branch_id=?', (branch_id,))
        policy, active = automatic_policy(connection, branch_id)
        if wake['status'] != 'pending' or not wake['allowance']:
            return None
        if not active:
            return {'inactive': True, 'wakeup': wake}
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        body = BackfillPreview(expected_revision=branch['revision'], batch_size=policy.batch_size,
                               max_batches=min(wake['allowance'], policy.max_batches))
        pending = {row['node_id'] for row in many(connection, 'SELECT node_id FROM summary_pending WHERE branch_id=?', (branch_id,))}
        return {'wakeup': wake, 'body': body, 'plan': batch_plan(connection, branch_id, body, pending)}


def record_automatic(database, prepared):
    if not prepared:
        return None
    with database.connect(write=True) as connection:
        wake = prepared['wakeup']
        current = one(connection, 'SELECT * FROM summary_wakeups WHERE id=?', (wake['id'],))
        require(current == wake, 'Accepted prose changed while maintenance was preparing. It will be reconsidered.', 409)
        if prepared.get('inactive'):
            connection.execute("UPDATE summary_wakeups SET status='paused',revision=revision+1 WHERE id=?", (wake['id'],))
            return None
        plan = prepared['plan']
        if plan['runs']:
            guard_batch(connection, plan, prepared['body'])
        for node_id in plan['completed_nodes']:
            connection.execute('DELETE FROM summary_pending WHERE branch_id=? AND node_id=?', (wake['branch_id'], node_id))
        remaining = wake['allowance'] - len(plan['runs'])
        status = 'limited' if plan['eligible_count'] > plan['selected_count'] else 'idle'
        connection.execute('UPDATE summary_wakeups SET status=?,allowance=?,revision=revision+1,error=? WHERE id=?',
                           (status, remaining, '', wake['id']))
        return insert_batch(connection, plan, 'automatic') if plan['runs'] else None


def require_batch_enabled(connection, batch):
    story = one(connection, 'SELECT s.* FROM stories s JOIN branches b ON b.story_id=s.id WHERE b.id=?', (batch['branch_id'],))
    require_agent(connection, 'memory-summary', story)
    if batch['kind'] == 'automatic':
        _, active = automatic_policy(connection, batch['branch_id'])
        require(active, 'Automatic summaries are disabled. Saved requests are preserved.', 409)
