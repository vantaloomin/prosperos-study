from server.agent_switches import require_agent
from server.database import one
from server.memory.summary_context import parse_summary
from server.workflow.runner import ReviewRunner


class SummaryRunner(ReviewRunner):
    prefix = 'summary'
    label = 'Story memory summary'

    def parse_result(self, output, snapshot):
        return parse_summary(output, snapshot)

    def retry(self, job_id):
        with self.database.connect() as connection:
            story = one(connection, 'SELECT s.* FROM stories s JOIN branches b ON b.story_id=s.id '
                        'JOIN summary_runs r ON r.branch_id=b.id JOIN summary_jobs j ON j.run_id=r.id WHERE j.id=?', (job_id,))
            require_agent(connection, 'memory-summary', story)
        return super().retry(job_id)
