from server.archives.chance import validate_tables
from server.assessment.context import parse_assessment
from server.assessment.decision import apply_opportunity
from server.database import decode, one
from server.errors import require
from server.lore.runtime import attach_lore
from server.mechanics.engine import resolve_beat
from server.mechanics.models import Beat, RngSettings
from server.mechanics.state import node_state


def validate_assessments(connection, data):
    jobs = {job['id']: job for job in data['assessment_jobs']}
    runs = {run['id']: run for run in data['assessment_runs']}
    for job in jobs.values():
        snapshot = decode(job['snapshot'])
        frozen = decode(runs[job['run_id']]['snapshot'])
        require(job['step'] == snapshot['step'] == 'beat-assessment', 'Invalid assessment role.')
        expected_context = decode(frozen['writer_snapshot']['content'])
        expected_context.pop('private_background', None)
        require(decode(snapshot['content'])['context'] == expected_context,
                'An assessment must use its saved writer context.')
        validate_report(job, snapshot)
    for attempt in data['assessment_attempts']:
        validate_report(attempt, decode(jobs[attempt['job_id']]['snapshot']))
    for run in runs.values():
        validate_assessment(connection, run, jobs)


def validate_report(job, snapshot):
    if job['status'] == 'done':
        require(parse_assessment(job['output'], snapshot) == decode(job['result']),
                'An assessment report disagrees with its validated output.')


def validate_assessment(connection, run, jobs):
    frozen = decode(run['snapshot'])
    require(frozen['branch'] == frozen['writer_snapshot']['branch'], 'Assessment and writer origins differ.')
    require(run['head_key'] == (frozen['branch']['head_id'] or ''), 'Assessment boundary differs from its origin.')
    require(frozen['before'] == node_state(connection, frozen['branch']['head_id']), 'Assessment starts from altered mechanics.')
    require(run['stopped'] in {0, 1}, 'Invalid assessment stop state.')
    validate_tables(connection, frozen)
    if run['selected_job_id']:
        job = jobs[run['selected_job_id']]
        require(job['run_id'] == run['id'] and job['status'] == 'done', 'Selected assessment belongs to another run or is unfinished.')
    require(bool(run['selected_job_id']) == bool(run['opportunity_id']), 'An assessment selection has no saved chance result.')
    require(not run['opportunity_id'] or run['generation_id'], 'Selected assessment has no writer request.')
    if run['generation_id']:
        validate_writer(connection, run, frozen, jobs)


def validate_writer(connection, run, frozen, jobs):
    generation = one(connection, 'SELECT * FROM generations WHERE id=?', (run['generation_id'],))
    expected = frozen['writer_snapshot']
    if run['opportunity_id']:
        opportunity = one(connection, 'SELECT * FROM mechanic_opportunities WHERE id=?', (run['opportunity_id'],))
        require(opportunity['branch_id'] == run['branch_id'] and opportunity['head_key'] == run['head_key'],
                'Assessment chance belongs to another boundary.')
        result = decode(opportunity['snapshot'])
        if result.get('assessment_id') == run['id']:
            validate_roll(run, frozen, result, jobs[run['selected_job_id']])
        apply_opportunity(expected, frozen['writer_profiles'], opportunity['id'], result)
    require(decode(generation['snapshot']) == expected, 'Assessment dispatched altered writer input.')


def validate_roll(run, frozen, actual, job):
    expected = resolve_beat(frozen['tables'], RngSettings.model_validate(frozen['settings']),
                            Beat.model_validate(decode(job['result'])['beat']), frozen['before'], frozen['seed'], False)
    if frozen['writer_snapshot'].get('lore_context'):
        attach_lore(expected, frozen['writer_snapshot']['lore_context'])
    expected.update(branch=frozen['branch'], story_revision=frozen['story_revision'], reroll_of=None,
                    assessment_id=run['id'], assessment_job_id=job['id'])
    if 'background_state_id' in frozen['writer_snapshot']:
        expected['background_state_id'] = frozen['writer_snapshot']['background_state_id']
    require(expected == actual, 'Assessment chance differs from its saved seed, report or tables.')
