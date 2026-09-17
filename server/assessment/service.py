from server.assessment.decision import finish_assessment
from server.assessment.models import AssessmentDecision
from server.database import decode, many, one
from server.errors import require
from server.generations import stale_target
from server.operations import previous, remember


def job_view(row):
    result = {**row, **{key: decode(row[key]) for key in ('snapshot', 'result', 'usage')}}
    result['snapshot']['profile'].pop('credential_ref', None)
    return result


class Assessments:
    def __init__(self, database):
        self.database = database

    def detail(self, run_id):
        with self.database.connect() as connection:
            run = one(connection, 'SELECT * FROM assessment_runs WHERE id=?', (run_id,))
            snapshot = decode(run['snapshot'])
            _, stale = stale_target(connection, snapshot['writer_snapshot'])
            for profile in snapshot['writer_profiles']:
                profile.pop('credential_ref', None)
            jobs = many(connection, 'SELECT * FROM assessment_jobs WHERE run_id=? ORDER BY rowid', (run_id,))
            return {**run, 'snapshot': snapshot, 'stale': stale, 'jobs': [job_view(job) for job in jobs]}

    def list(self, branch_id):
        with self.database.connect() as connection:
            return many(connection, 'SELECT id,head_key,generation_id,created_at FROM assessment_runs WHERE branch_id=? ORDER BY rowid DESC', (branch_id,))

    def pending(self, run_id):
        with self.database.connect() as connection:
            return many(connection, "SELECT id FROM assessment_jobs WHERE run_id=? AND status='queued'", (run_id,))

    def decide(self, run_id, body, automatic=False):
        payload = {'run_id': run_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'choose_assessment', payload)
            if cached is not None:
                return cached
            run = one(connection, 'SELECT * FROM assessment_runs WHERE id=?', (run_id,))
            if run['generation_id']:
                return {'id': run['generation_id']}
            require(not automatic or not run['stopped'], 'Assessment stopped; choose explicitly to continue.', 409)
            result = finish_assessment(connection, run, body)
            return remember(connection, body.operation_id, 'choose_assessment', payload, result)

    def auto_finish(self, job_id):
        with self.database.connect() as connection:
            job = one(connection, 'SELECT * FROM assessment_jobs WHERE id=?', (job_id,))
            jobs = many(connection, 'SELECT id FROM assessment_jobs WHERE run_id=?', (job['run_id'],))
        if job['status'] != 'done' or len(jobs) != 1:
            return None
        return self.decide(job['run_id'], AssessmentDecision(operation_id=f'assessment-{job_id}', job_id=job_id), automatic=True)

    def stop(self, run_id):
        with self.database.connect(write=True) as connection:
            one(connection, 'SELECT id FROM assessment_runs WHERE id=?', (run_id,))
            connection.execute('UPDATE assessment_runs SET stopped=1 WHERE id=?', (run_id,))
            return many(connection, "SELECT id FROM assessment_jobs WHERE run_id=? AND status IN ('queued','running')", (run_id,))

    def retryable(self, job_id):
        with self.database.connect(write=True) as connection:
            job = one(connection, 'SELECT run_id FROM assessment_jobs WHERE id=?', (job_id,))
            run = one(connection, 'SELECT * FROM assessment_runs WHERE id=?', (job['run_id'],))
            require(not run['generation_id'], 'This assessment already started its writer. Open the saved drafts.', 409)
            _, stale = stale_target(connection, decode(run['snapshot'])['writer_snapshot'])
            require(not stale, 'This assessment belongs to an earlier Story state.', 409)
            connection.execute("UPDATE assessment_runs SET stopped=0,error='' WHERE id=?", (run['id'],))

    def attempts(self, job_id):
        with self.database.connect() as connection:
            rows = many(connection, 'SELECT * FROM assessment_attempts WHERE job_id=? ORDER BY attempt DESC', (job_id,))
            return [{**row, 'result': decode(row['result']), 'usage': decode(row['usage'])} for row in rows]
