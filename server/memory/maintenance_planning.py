"""Bounded backfill and coalesced batches, compiled outside the write transaction."""
from server.database import decode, many, one
from server.errors import require
from server.memory.summary_context import prepared_from_sources, source_chunks, source_evidence
from server.memory.summary_service import guard_prepared, preview_view
from server.stories import check_revision
from server.workflow.context import snapshot_hash, validate_job_budget


def coverage_rows(connection, story_id):
    return many(connection, 'SELECT r.id,r.snapshot FROM summary_runs r JOIN branches b ON b.id=r.branch_id '
                'WHERE b.story_id=? ORDER BY r.rowid', (story_id,))


def source_key(link):
    return (link['node_id'], link['start'], link['end'], link['sha256'])


def requested_sources(rows, path_ids):
    covered = set()
    for row in rows:
        links = decode(row['snapshot'])['source_links']
        if all(link['node_id'] in path_ids for link in links):
            covered.update(source_key(link) for link in links)
    return covered


def batch_plan(connection, branch_id, body, pending_nodes=None):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    chunks = source_chunks(connection, branch['head_id'])
    path_ids = {node['id'] for node, _ in chunks}
    rows = coverage_rows(connection, story['id'])
    covered = requested_sources(rows, path_ids)
    sources = [source_evidence(node, chunk) for node, chunk in chunks if pending_nodes is None or node['id'] in pending_nodes]
    available = [source for source in sources if source_key(source) not in covered]
    runs = planned_runs(connection, branch, story, available, body)
    selected_count = sum(len(run['source_links']) for run in runs)
    chosen = available[:selected_count]
    waiting_nodes = {item['node_id'] for item in available[selected_count:]}
    return {'branch': branch, 'story_revision': story['revision'], 'batch_size': body.batch_size,
            'max_batches': body.max_batches, 'eligible_count': len(available), 'selected_count': len(chosen),
            'completed_nodes': sorted({item['node_id'] for item in sources} - waiting_nodes),
            'covered_count': len(sources) - len(available), 'coverage_stamp': [row['id'] for row in rows], 'runs': runs}


def batch_preview(plan):
    return {'preview_hash': snapshot_hash(plan), 'eligible_count': plan['eligible_count'], 'selected_count': plan['selected_count'],
            'covered_count': plan['covered_count'], 'batch_count': len(plan['runs']),
            'request_count': sum(len(run['jobs']) for run in plan['runs']),
            'batches': [preview_view(run) for run in plan['runs']]}


def guard_batch(connection, plan, body):
    require(bool(plan['runs']), 'No new excerpts are available in this selection. Existing requests remain in Story memory.', 409)
    guard_prepared(connection, plan['runs'][0], body)
    current = [row['id'] for row in many(connection, 'SELECT r.id FROM summary_runs r JOIN branches b ON b.id=r.branch_id '
                                       'WHERE b.story_id=? ORDER BY r.rowid', (plan['branch']['story_id'],))]
    require(current == plan['coverage_stamp'], 'Other summary requests were saved. Preview again to avoid duplicate work.', 409)


def planned_runs(connection, branch, story, available, body):
    result, cursor = [], 0
    while cursor < len(available) and len(result) < body.max_batches:
        run = fitting_run(connection, branch, story, available[cursor:cursor + body.batch_size], body.profile_ids)
        result.append(run)
        cursor += len(run['source_links'])
    return result


def fitting_run(connection, branch, story, sources, profile_ids):
    while sources:
        run = prepared_from_sources(connection, branch, story, sources, profile_ids, validate_budget=False)
        jobs = run['jobs']
        fits = all(job['estimated_input_tokens'] <= job['profile']['config']['context_tokens'] - job['profile']['config']['max_output_tokens'] for job in jobs)
        if fits or len(sources) == 1:
            validate_job_budget([job['profile'] for job in jobs], jobs[0]['estimated_input_tokens'])
            return run
        sources = sources[:-1]
