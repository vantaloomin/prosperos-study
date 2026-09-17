from server.database import one
from server.lore.runtime import current_lore
from server.mechanics.config import read_settings
from server.mechanics.storage import opportunity_stale, pending_opportunity


def inspect_branch(database, branch_id):
    with database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
        _, selection = current_lore(connection, branch, read_settings(story).enabled)
        pending = pending_opportunity(connection, branch, story)
        prepared = None
        if pending and not opportunity_stale(pending, branch, story):
            prepared = pending['snapshot'].get('lore')
        return {'current': selection, 'prepared': prepared,
                'notice': 'Reading this view makes no rolls or state changes. Prepared choices apply only when that beat is used.'}
