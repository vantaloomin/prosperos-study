from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.memory.summary_catalog import SUMMARY_KEY
from server.memory.summary_context import prepare_summary, source_chunks, source_evidence
from server.memory.summary_versions import applicable_versions, publish_version
from server.operations import previous, remember
from server.stories import check_revision
from server.workflow.context import job_snapshot, snapshot_hash
from server.workflow.models import ReviewStep
from server.workflow.reviews import job_view


def preview_view(snapshot):
    return {'preview_hash': snapshot_hash(snapshot), 'source_count': len(snapshot['source_links']),
            'request_count': len(snapshot['jobs']), 'jobs': [{
                'profile_name': job['profile']['name'], 'model': job['profile']['config']['model'],
                'estimated_input_tokens': job['estimated_input_tokens'], 'prompt_version': job['prompt']['number'],
                'content': job['content'], 'instructions': job['prompt']['template']} for job in snapshot['jobs']]}


def guard_prepared(connection, snapshot, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (snapshot['branch']['id'],))
    check_revision(branch, body.expected_revision)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    require(branch == snapshot['branch'] and story['revision'] == snapshot['story_revision'],
            'The Story changed. Preview these summary inputs again.', 409)
    selection = ReviewStep(key=SUMMARY_KEY, profile_ids=body.profile_ids)
    current = job_snapshot(connection, story, selection, {}, validate_budget=False)
    require([(job['profile'], job['prompt']) for job in current] == [(job['profile'], job['prompt']) for job in snapshot['jobs']],
            'Model settings or instructions changed. Preview again.', 409)


class Summaries:
    def __init__(self, database):
        self.database = database

    def sources(self, branch_id, offset=0):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            chunks = source_chunks(connection, branch['head_id'])
            return {'items': [source_evidence(node, chunk) for node, chunk in chunks[offset:offset + 12]],
                    'matches': len(chunks), 'offset': offset,
                    'next_offset': offset + 12 if offset + 12 < len(chunks) else None,
                    'revision': branch['revision']}

    def preview(self, branch_id, body):
        with self.database.connect() as connection:
            return preview_view(prepare_summary(connection, branch_id, body))

    def create(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect() as connection:
            cached = previous(connection, body.operation_id, 'summary', payload)
            if cached is not None:
                return cached
            snapshot = prepare_summary(connection, branch_id, body)
            require(snapshot_hash(snapshot) == body.preview_hash, 'These inputs changed. Preview again.', 409)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'summary', payload)
            if cached is not None:
                return cached
            guard_prepared(connection, snapshot, body)
            result = insert_run(connection, snapshot)
            return remember(connection, body.operation_id, 'summary', payload, result)

    def history(self, branch_id, offset=0):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            return many(connection, 'SELECT r.id,r.branch_id,b.name AS branch_name,r.created_at FROM summary_runs r '
                        'JOIN branches b ON b.id=r.branch_id WHERE b.story_id=? ORDER BY r.rowid DESC LIMIT 50 OFFSET ?',
                        (branch['story_id'], offset))

    def detail(self, run_id, branch_id):
        with self.database.connect() as connection:
            run = one(connection, 'SELECT * FROM summary_runs WHERE id=?', (run_id,))
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            snapshot = decode(run['snapshot'])
            require(snapshot['branch']['story_id'] == branch['story_id'], 'This request belongs to another Story.', 409)
            jobs = many(connection, 'SELECT * FROM summary_jobs WHERE run_id=? ORDER BY rowid', (run_id,))
            versions = many(connection, 'SELECT * FROM summary_versions WHERE run_id=? ORDER BY rowid DESC', (run_id,))
            return {**run, 'snapshot': snapshot, 'jobs': [job_view(job) for job in jobs],
                    'current_version': applicable_versions(connection, branch).get(run_id),
                    'versions': [{**version, 'result': decode(version['result'])} for version in versions]}

    def attempts(self, job_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM summary_jobs WHERE id=?', (job_id,))
            rows = many(connection, 'SELECT * FROM summary_attempts WHERE job_id=? ORDER BY attempt DESC', (job_id,))
            return [{**row, 'result': decode(row['result']), 'usage': decode(row['usage'])} for row in rows]

    def publish(self, run_id, body):
        return publish_version(self.database, run_id, body)


def insert_run(connection, snapshot):
    existing = connection.execute('SELECT id FROM summary_runs WHERE branch_id=? AND request_key=?',
                                  (snapshot['branch']['id'], snapshot['request_key'])).fetchone()
    if existing:
        return {'id': existing['id'], 'job_ids': []}
    run_id, job_ids = identifier(), []
    jobs = snapshot.pop('jobs')
    connection.execute('INSERT INTO summary_runs VALUES (?,?,?,?,?)',
        (run_id, snapshot['branch']['id'], snapshot['request_key'], encode(snapshot), now()))
    for job in jobs:
        job_id = identifier()
        connection.execute("INSERT INTO summary_jobs (id,run_id,step,snapshot,status,updated_at) VALUES (?,?,?,?,'queued',?)",
            (job_id, run_id, job['step'], encode(job), now()))
        job_ids.append(job_id)
    return {'id': run_id, 'job_ids': job_ids}
