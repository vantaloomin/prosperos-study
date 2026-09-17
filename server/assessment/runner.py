from server.assessment.context import parse_assessment
from server.assessment.service import Assessments
from server.database import one
from server.errors import DomainError
from server.workflow.runner import ReviewRunner


class AssessmentRunner(ReviewRunner):
    prefix = 'assessment'
    label = 'beat assessment'

    def __init__(self, database, writer):
        super().__init__(database, writer.provider)
        self.writer = writer

    def parse_result(self, output, snapshot):
        return parse_assessment(output, snapshot)

    async def run(self, job_id):
        await super().run(job_id)
        try:
            result = Assessments(self.database).auto_finish(job_id)
            if result:
                for candidate in self.writer.pending(result['id']):
                    self.writer.start(candidate['id'])
        except DomainError as error:
            with self.database.connect(write=True) as connection:
                job = one(connection, 'SELECT run_id FROM assessment_jobs WHERE id=?', (job_id,))
                connection.execute('UPDATE assessment_runs SET error=? WHERE id=?', (error.message, job['run_id']))

    def retry(self, job_id):
        Assessments(self.database).retryable(job_id)
        return super().retry(job_id)

    def stop_superseded(self, branch_id):
        with self.database.connect() as connection:
            jobs = connection.execute("SELECT j.id FROM assessment_jobs j JOIN assessment_runs r ON r.id=j.run_id "
                                       "WHERE r.branch_id=? AND r.stopped=1 AND j.status IN ('queued','running')", (branch_id,)).fetchall()
        for job in jobs:
            self.cancel(job['id'])
