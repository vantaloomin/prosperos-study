"""Observed attempt timing; polling is never counted as provider activity."""
from server.database import many, now


def start_activity(connection, candidate_id, attempt):
    connection.execute('INSERT INTO candidate_activity (candidate_id,attempt,started_at) VALUES (?,?,?)',
                       (candidate_id, attempt, now()))


def activity_rows(connection, generation_id):
    rows = many(connection, 'SELECT a.* FROM candidate_activity a JOIN candidates c ON c.id=a.candidate_id '
                'WHERE c.generation_id=? AND c.attempt=a.attempt', (generation_id,))
    return {row['candidate_id']: row for row in rows}


def save_activity(connection, candidate_id, state, final):
    connection.execute('UPDATE candidate_activity SET first_text_at=COALESCE(first_text_at,?), '
                       'last_event_at=COALESCE(?,last_event_at),finished_at=?,error_kind=? '
                       'WHERE candidate_id=? AND attempt=(SELECT attempt FROM candidates WHERE id=?)',
                       (state.get('first_text_at'), state.get('last_event_at'), now() if final else None,
                        state.get('error_kind', ''), candidate_id, candidate_id))


def interrupt_activity(connection):
    connection.execute("UPDATE candidate_activity SET finished_at=?,error_kind='interrupted' "
                       "WHERE finished_at IS NULL AND candidate_id IN "
                       "(SELECT id FROM candidates WHERE status IN ('running','queued'))", (now(),))


def generation_summaries(connection, branch_id):
    # One compact joined projection; no frozen context or output text on the history request.
    rows = many(connection, 'SELECT g.id,g.branch_id,g.created_at,c.status,c.accepted_branch_id '
                'FROM generations g LEFT JOIN candidates c ON c.generation_id=g.id '
                'WHERE g.branch_id=? ORDER BY g.created_at DESC,g.rowid DESC,c.rowid', (branch_id,))
    result = {}
    for row in rows:
        run = result.setdefault(row['id'], {key: row[key] for key in ('id', 'branch_id', 'created_at')})
        run.setdefault('statuses', []).append(row['status'])
        run['unaccepted'] = run.get('unaccepted', False) or row['accepted_branch_id'] is None
    return list(result.values())
