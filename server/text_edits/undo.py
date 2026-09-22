from server.text_edits.models import TextTarget
from server.text_edits.selection import whole_text
from server.text_edits.service import apply_in, create_in, proposal_view, read_receipt, run
from server.text_edits.targets import read_target


def undo_receipt(database, identity, body):
    def action(connection):
        original = read_receipt(connection, identity)
        applied = connection.execute('SELECT id FROM text_edit_receipts WHERE undo_of=?', (identity,)).fetchone()
        if applied:
            return {'status': 'applied', 'receipt': read_receipt(connection, applied['id'])}
        pending = connection.execute("SELECT id FROM text_edit_proposals WHERE undo_of=? AND status IN ('pending','conflict') ORDER BY created_at DESC LIMIT 1", (identity,)).fetchone()
        if pending:
            return {'status': 'conflict', 'proposal': proposal_view(connection, pending['id'])}
        ref = TextTarget.model_validate(original['after_target']['ref'])
        current = read_target(connection, ref)
        conflict = current['text'] != original['after_target']['text']
        target = original['after_target'] if conflict else current
        proposal = create_in(connection, target, whole_text(target['text']), 'update', original['before_target']['text'],
            'Restore the text before this applied change.', origin={'kind': 'author'}, undo_of=identity,
            status='conflict' if conflict else 'pending')
        if conflict:
            return {'status': 'conflict', 'proposal': proposal, 'current_target': current}
        return {'status': 'applied', 'receipt': apply_in(connection, proposal['id'], proposal['revision'], 'Restored telling', body.acknowledge_state_reset, database=database)}
    return run(database, body, 'text-edit-undo', identity, action)
