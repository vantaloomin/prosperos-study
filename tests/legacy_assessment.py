"""Construct pre-v0.6.2 saved requests to exercise their preserved replay path."""
from server.agent_switches import agent_enabled
from server.assessment.context import assessment_needed, assessment_snapshot
from server.assessment.writing import WritingRequests, saved_boundary, start_assessment
from server.database import one
from server.generation_preparation import prepare_writer


def legacy_create(database, branch_id, body):
    with database.connect(write=True) as connection:
        prepared = prepare_writer(connection, branch_id, body)
        writer = prepared.snapshot
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (writer['branch']['story_id'],))
        if (agent_enabled(connection, 'beat-assessment', story) and assessment_needed(story, writer, body)
                and not saved_boundary(connection, writer['branch'])):
            existing = connection.execute('SELECT id FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                          (branch_id, writer['branch']['head_id'])).fetchone()
            if existing:
                return {'assessment_id': existing['id']}
            return start_assessment(connection, assessment_snapshot(connection, story, writer, prepared.profiles, body))
    return WritingRequests(database).create(branch_id, body)


def dispatch(client, result):
    async def launch():
        if result.get('assessment_id'):
            from server.assessment.service import Assessments
            for job in Assessments(client.app.state.database).pending(result['assessment_id']):
                client.app.state.assessment_runner.start(job['id'])
        else:
            for job in client.app.state.runner.pending(result['id']):
                client.app.state.runner.start(job['id'])
    client.portal.call(launch)
    return result
