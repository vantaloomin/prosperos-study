"""Recipe archives keep compiler evidence frozen and remap live authorities separately."""
from server.archives.format import RECIPE_TABLES, V50_TABLES
from server.archives.remap import fields
from server.archives.text_edit_versions import bind_restored_editions
from server.archives.text_edits import remap_text_edit
from server.database import decode, encode, one
from server.errors import require
from server.text_edits.service import read_proposal
from server.writing.recipe_state import progress, read_jobs, read_run


def recipe_references(data):
    result = {key: set() for key in ('profiles', 'prompt_versions', 'roll_table_versions')}
    for row in data.get('recipe_runs', []):
        snapshot, bindings = decode(row['snapshot']), decode(row['bindings'])
        for stage in snapshot['plan']:
            for template in stage['templates']:
                result['profiles'].add(bindings[template['profile']['profile_id']])
                result['prompt_versions'].update(bindings[item['id']] for item in [template['prompt'], *template['prompt_sections']])
        result['roll_table_versions'].update(bindings[table['id']] for table in snapshot['chance']['tables'].values())
    return result


def remap_run(connection, row, mapping):
    target = remap_text_edit('text_edit_proposals', {'target': row['target']}, mapping)
    target = bind_restored_editions(connection, 'text_edit_proposals', target)
    return {**fields(row, mapping), 'target': target['target'],
            'bindings': encode({key: mapping[value] for key, value in decode(row['bindings']).items()})}


def validate_recipes(connection, data):
    from server.archives.recipe_validation import validate_output, validate_run, validate_stages
    for row in data['recipe_runs']:
        run, jobs = read_run(connection, row['id']), read_jobs(connection, row['id'])
        validate_run(connection, run, data)
        validate_stages(run, jobs)
        state = progress(run, jobs)
        result = connection.execute('SELECT * FROM recipe_results WHERE run_id=?', (row['id'],)).fetchone()
        require(bool(result) == bool(state['status'] == 'complete' and state['last_prose']),
                'A completed text recipe needs exactly one final proposal; unfinished or review-only runs cannot own one.')
        if result:
            require(result['job_id'] == state['last_prose'], 'A recipe result uses another step or run.')
            proposal = read_proposal(connection, result['proposal_id'])
            require(proposal['origin'] == {'kind': 'recipe', 'run_id': run['id'], 'job_id': result['job_id']}
                    and proposal['target'] == run['target'] and proposal['selection'] == run['snapshot']['selection']
                    and proposal['action'] == run['snapshot']['action'] and not proposal['undo_of'],
                    'A recipe proposal changed its original destination or action.')
            # Authors may edit the proposal; the job output remains its immutable generated version.
        by_id = {job['id']: job for job in jobs}
        for attempt in data['recipe_attempts']:
            if attempt['job_id'] in by_id:
                job = by_id[attempt['job_id']]
                require(0 <= attempt['attempt'] <= job['attempt'], 'A recipe attempt is out of sequence.')
                validate_output(attempt, job['snapshot'])


def validate_proposal_origin(connection, proposal):
    origin = proposal['origin']
    require(set(origin) == {'kind', 'run_id', 'job_id'}, 'An edit has an incomplete recipe origin.')
    run = read_run(connection, origin['run_id'])
    result = one(connection, 'SELECT * FROM recipe_results WHERE run_id=?', (run['id'],))
    # Rebases and Undo retain origin but may point at the later telling created by an edit.
    original = read_proposal(connection, result['proposal_id'])
    require(proposal['story_id'] == run['story_id'] and result['job_id'] == origin['job_id'],
            'A recipe edit refers to another Story or step.')
    if not proposal['undo_of']:
        require(proposal['target']['ref'] == original['target']['ref'], 'A rebased recipe edit changed its destination.')


def upgrade_recipes(document):
    if document['version'] == 50:
        require(set(document['data']) == set(V50_TABLES), 'Version 50 needs its original record groups.')
        require(all(decode(row['origin']).get('kind') in {'author', 'companion'}
                    for table in ('text_edit_proposals', 'text_edit_receipts') for row in document['data'][table]),
                'Version 50 does not include recipe execution origins.')
        document['data'].update({table: [] for table in RECIPE_TABLES})
        document['version'] = 51
    return document
