"""Prepare the next beat at acceptance, without starting or changing a writer."""
from starlette.concurrency import run_in_threadpool

from server.agent_switches import agent_enabled
from server.assessment.context import assessment_plan, eligible_head, seed_assessment
from server.assessment.writing import saved_boundary, start_assessment
from server.background.storage import state_id
from server.database import decode, many, one
from server.errors import DomainError, require
from server.generation_context import generation_snapshot
from server.generation_models import ContextPreviewRequest
from server.mechanics.config import configured_tables, read_settings
from server.memory.control_state import control_head
from server.profiles import resolve_profile
from server.prompts import prompt_snapshot


def written_at_boundary(connection, branch):
    return connection.execute("SELECT id FROM generations WHERE branch_id=? "
                              "AND json_extract(snapshot,'$.branch.revision')=? LIMIT 1",
                              (branch['id'], branch['revision'])).fetchone() is not None


def preparation_stale(connection, snapshot, *, check_written=False):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (snapshot['branch']['id'],))
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    settings = read_settings(story)
    if (branch['revision'] != snapshot['branch']['revision'] or branch['head_id'] != snapshot['branch']['head_id']
            or story['revision'] != snapshot['story_revision'] or not settings.enabled
            or not settings.automatic_assessment or not agent_enabled(connection, 'beat-assessment', story)):
        return True
    writer = snapshot['writer_snapshot']
    if (state_id(connection, branch['id']) != writer.get('background_state_id')
            or control_head(connection, branch['id']) != writer.get('memory_controls_version_id')):
        return True
    if check_written and written_at_boundary(connection, branch):
        return True
    try:
        profile = resolve_profile(connection, story, 'beat-assessment')
        prompt = prompt_snapshot(connection, 'beat-assessment', story)
        tables = configured_tables(connection, settings)
    except DomainError:
        return True
    return (profile['id'] != snapshot['assessment_profile_id'] or prompt['id'] != snapshot['assessment_prompt_version_id']
            or {key: item['id'] for key, item in tables.items()} != {key: item['id'] for key, item in snapshot['tables'].items()})


def prepare_accepted(database, branch_id, node_id):
    with database.connect(write=True) as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
        settings = read_settings(story)
        if not (branch['head_id'] == node_id and settings.enabled and settings.automatic_assessment
                and agent_enabled(connection, 'beat-assessment', story)):
            return None
        existing = connection.execute('SELECT id FROM assessment_runs WHERE branch_id=? AND head_key=?', (branch_id, node_id)).fetchone()
        if existing or saved_boundary(connection, branch) or written_at_boundary(connection, branch):
            return None
        body = ContextPreviewRequest(expected_revision=branch['revision'], use_prepared_beat=False)
        writer, profiles = generation_snapshot(connection, branch_id, body, validate_budget=False)
        if eligible_head(writer) != node_id:
            return None
        plan = assessment_plan(connection, story, writer, profiles, body)
        job = plan['jobs'][0]
        plan.update(purpose='post-acceptance', assessment_profile_id=job['profile']['id'],
                    assessment_prompt_version_id=job['prompt']['id'])
        return start_assessment(connection, seed_assessment(plan))


async def after_acceptance(request, result):
    """The acceptance is committed first; a preparation error cannot undo it."""
    accepted = result.get('state', result).get('accepted', result)
    if not accepted or not accepted.get('node_id'):
        return result
    try:
        prepared = await run_in_threadpool(prepare_accepted, request.app.state.database,
                                           accepted['branch_id'], accepted['node_id'])
        if prepared:
            with request.app.state.database.connect() as connection:
                jobs = many(connection, 'SELECT id FROM assessment_jobs WHERE run_id=?', (prepared['assessment_id'],))
            for job in jobs:
                request.app.state.assessment_runner.start(job['id'])
    except DomainError as error:
        return {**result, 'assessment_error': error.message}
    return result


def finish_preparation(connection, run, body):
    from server.assessment.decision import opportunity_for

    snapshot = decode(run['snapshot'])
    require(not run['stopped'] and not preparation_stale(connection, snapshot, check_written=True),
            'This beat preparation was skipped or belongs to an earlier Story state. Writing can continue without it.', 409)
    if body.without_chance:
        connection.execute('UPDATE assessment_runs SET stopped=1 WHERE id=?', (run['id'],))
        return {'assessment_id': run['id'], 'opportunity_id': None}
    require(body.job_id, 'Choose a completed assessment.')
    if run['opportunity_id']:
        require(body.job_id == run['selected_job_id'], 'This boundary already has its saved assessment.', 409)
        return {'assessment_id': run['id'], 'opportunity_id': run['opportunity_id']}
    job = one(connection, 'SELECT * FROM assessment_jobs WHERE id=? AND run_id=?', (body.job_id, run['id']))
    require(job['status'] == 'done', 'Choose a completed, validated assessment.', 409)
    opportunity_id, _ = opportunity_for(connection, run, snapshot, job)
    connection.execute('UPDATE assessment_runs SET selected_job_id=?,opportunity_id=?,error=? WHERE id=?',
                       (body.job_id, opportunity_id, '', run['id']))
    return {'assessment_id': run['id'], 'opportunity_id': opportunity_id}
