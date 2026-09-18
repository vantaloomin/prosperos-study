"""Immutable author decisions, scoped to the accepted path at publication."""
from server.branches import path_nodes
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.stories import check_revision


def applicable_versions(connection, branch):
    path = {node['id'] for node in path_nodes(connection, branch['head_id'])}
    rows = many(connection, 'SELECT v.*,r.snapshot FROM summary_versions v JOIN summary_runs r ON r.id=v.run_id '
                'JOIN branches b ON b.id=r.branch_id WHERE b.story_id=? ORDER BY v.rowid DESC', (branch['story_id'],))
    selected = {}
    for row in rows:
        snapshot = decode(row.pop('snapshot'))
        eligible = row['node_id'] in path and all(link['node_id'] in path for link in snapshot['source_links'])
        if eligible and row['run_id'] not in selected:
            selected[row['run_id']] = {**row, 'result': decode(row['result']), 'source_links': snapshot['source_links']}
    return selected


def publish_version(database, run_id, body):
    from server.memory.summary_context import validate_dependencies, validate_summary
    payload = {'run_id': run_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        cached = previous(connection, body.operation_id, 'summary-publish', payload)
        if cached is not None:
            return cached
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (body.branch_id,))
        check_revision(branch, body.expected_revision)
        run = one(connection, 'SELECT * FROM summary_runs WHERE id=?', (run_id,))
        snapshot = decode(run['snapshot'])
        require(snapshot['branch']['story_id'] == branch['story_id'], 'This summary belongs to a different Story.', 409)
        job = one(connection, 'SELECT * FROM summary_jobs WHERE id=?', (body.job_id,))
        require(job['run_id'] == run_id and job['status'] == 'done', 'Choose a completed summary from this request.', 409)
        validate_dependencies(connection, snapshot, branch['head_id'])
        result = validate_summary(body.result, snapshot['content'])
        current = applicable_versions(connection, branch).get(run_id)
        require((current['id'] if current else None) == body.expected_version_id,
                'The saved summary changed. Reopen it before saving another version.', 409)
        version_id = identifier()
        connection.execute('INSERT INTO summary_versions VALUES (?,?,?,?,?,?,?,?,?,?)',
            (version_id, run_id, job['id'], body.expected_version_id, branch['id'], branch['head_id'],
             encode(result), int(body.enabled), 'reviewed', now()))
        return remember(connection, body.operation_id, 'summary-publish', payload, {'id': version_id})
