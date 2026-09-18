"""Coverage belongs to the selected informed report of the exact proposed draft."""
from server.database import decode, many
from server.scenes.state import reviewed_state


def report_coverage(result):
    if not result.get('coverage'):
        return None
    return {'summary': result['summary'], 'beats': result['coverage'], 'issues': [
        {'category': 'other', 'quote': item['quote'], 'explanation': item['explanation']}
        for item in result['findings'] if item.get('lens') == 'coverage']}


def selected_coverage(connection, run, job_ids=None):
    rows = many(connection, "SELECT j.*,r.snapshot AS review_snapshot,r.selections AS review_selections "
                "FROM review_jobs j JOIN review_runs r ON r.id=j.run_id WHERE j.status='done' "
                "AND json_extract(r.snapshot,'$.scene.id')=? ORDER BY r.rowid DESC,j.rowid DESC", (run['id'],))
    for row in rows:
        chosen = row['id'] in job_ids if job_ids is not None else decode(row['review_selections']).get(row['step']) == row['id']
        target = decode(row['review_snapshot'])['scene']
        if not chosen or reviewed_state(target['state']) != reviewed_state(run['state']):
            continue
        result = report_coverage(decode(row['result']))
        if result:
            return result
    return None
