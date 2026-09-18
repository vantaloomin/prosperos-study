"""Record cheap post-acceptance intent; no source traversal or inference in this hook."""
from server.agent_switches import agent_enabled
from server.database import decode, identifier, now, one
from server.memory.settings import memory_settings


def automatic_policy(connection, branch_id):
    story = one(connection, 'SELECT s.* FROM stories s JOIN branches b ON b.story_id=s.id WHERE b.id=?', (branch_id,))
    memory = memory_settings(decode(story['settings']).get('memory'))
    active = memory.mode == 'long' and memory.maintenance.enabled and agent_enabled(connection, 'memory-summary', story)
    return memory.maintenance, active


def enqueue_accepted(connection, branch_id, node_id):
    policy, active = automatic_policy(connection, branch_id)
    if not active or one(connection, 'SELECT role FROM nodes WHERE id=?', (node_id,))['role'] == 'ooc':
        return
    connection.execute('INSERT OR IGNORE INTO summary_pending VALUES (?,?,?,?)', (identifier(), branch_id, node_id, now()))
    # Coalesce accepted updates without adding their allowances together. A stopped
    # or interrupted queue never resumes just because another contribution arrives.
    connection.execute("INSERT INTO summary_wakeups VALUES (?,?,1,?,'pending','',?) ON CONFLICT(branch_id) DO UPDATE SET "
        "revision=revision+1,allowance=MAX(allowance,excluded.allowance),updated_at=excluded.updated_at,"
        "status=CASE WHEN status IN ('idle','limited','pending') THEN 'pending' ELSE status END",
        (identifier(), branch_id, policy.max_batches, now()))
