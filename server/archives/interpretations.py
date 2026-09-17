from server.background.interpretation_context import parse_interpretation
from server.background.targets import private_targets
from server.database import decode, one
from server.errors import require


def comparable_targets(targets):
    # Exact provider inputs retain historical IDs on import; live setup IDs are remapped.
    return {kind: [{**item, 'character': item['character']['name']} if 'character' in item else item
                   for item in entries] for kind, entries in targets.items()}


def validate_interpretations(connection, data):
    runs = {row['id']: decode(row['snapshot']) for row in data['background_runs']}
    jobs = {row['id']: row for row in data['background_jobs']}
    for run in runs.values():
        source = one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (run['background_state_id'],))
        expected = private_targets(decode(source['snapshot']))
        require(any(expected.values()) and comparable_targets(decode(run['content'])['targets']) == comparable_targets(expected),
                'Private targets differ from the enabled recorded draws.')
    for job in jobs.values():
        validate_job(connection, job, runs[job['run_id']])
    for attempt in data['background_attempts']:
        validate_output(attempt, decode(jobs[attempt['job_id']]['snapshot']))
    for state in data['background_states']:
        validate_selected_state(connection, state, jobs, runs)


def validate_output(row, snapshot):
    if row['status'] == 'done':
        require(decode(row['result']) == parse_interpretation(row['output'], snapshot),
                'Private interpretation differs from its validated output.')


def validate_job(connection, job, run):
    snapshot = decode(job['snapshot'])
    require(job['step'] == snapshot['step'] == 'background-interpretation', 'Invalid private interpretation role.')
    require(snapshot['content'] == run['content'], 'Private comparison inputs differ from their frozen run.')
    validate_output(job, snapshot)
    if job['selected_state_id']:
        state = one(connection, 'SELECT * FROM background_states WHERE id=?', (job['selected_state_id'],))
        require(job['status'] == 'done' and state['story_id'] == run['branch']['story_id']
                and state['previous_id'] == run['background_state_id'], 'A private selection has invalid ownership or origin.')
        selected = decode(state['snapshot']).get('interpretation', {})
        require(selected.get('job_id') == job['id'], 'A private selection points to another interpretation.')


def validate_selected_state(connection, state, jobs, runs):
    snapshot = decode(state['snapshot'])
    selected = snapshot.get('interpretation')
    if not selected:
        return
    job = jobs[selected['job_id']]
    run = runs[job['run_id']]
    require(selected['run_id'] == job['run_id'] and job['selected_state_id'] and job['status'] == 'done',
            'Private details have no completed selected interpretation.')
    require(state['story_id'] == run['branch']['story_id'] and selected['content'] == decode(job['result']),
            'Private details differ from their selected proposal or Story.')
    original = decode(one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (run['background_state_id'],))['snapshot'])
    require(all(snapshot[key] == original[key] for key in ('recipe', 'settings', 'result')),
            'Private details belong to different random draws or character versions.')
