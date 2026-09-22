from server.agent_switches import require_agent
from server.database import decode, many, one
from server.errors import require
from server.workflow.context import snapshot_hash
from server.workflow.readers import lens_task
from server.writing.recipe_bindings import bind_job
from server.writing.recipe_context import compile_job


def read_run(connection, run_id):
    row = one(connection, 'SELECT * FROM recipe_runs WHERE id=?', (run_id,))
    return {**row, **{key: decode(row[key]) for key in ('snapshot', 'bindings', 'target', 'chance')}}


def read_jobs(connection, run_id):
    return [{**row, **{key: decode(row[key]) for key in ('snapshot', 'result', 'usage')}} for row in many(
        connection, 'SELECT * FROM recipe_jobs WHERE run_id=? ORDER BY stage,rowid', (run_id,))]


def progress(run, jobs):
    draft, reviews, last_prose = None, [], None
    for index, stage in enumerate(run['snapshot']['plan']):
        if stage['skipped']:
            continue
        current = [job for job in jobs if job['stage'] == index]
        order = [template['step'] for template in stage['templates']]
        current.sort(key=lambda job: order.index(job['step']))
        if not current:
            return {'status': 'ready', 'stage': index, 'draft': draft, 'reviews': reviews, 'last_prose': last_prose}
        if any(job['status'] != 'done' for job in current):
            active = any(job['status'] in {'queued', 'running'} for job in current)
            return {'status': 'running' if active else 'needs-attention', 'stage': index, 'draft': draft, 'reviews': reviews, 'last_prose': last_prose}
        if stage['task'] == 'review':
            reviews = [job['result'] for job in current]
        else:
            draft, last_prose = current[0]['result']['replacement'], current[0]['id']
    return {'status': 'complete', 'stage': None, 'draft': draft, 'reviews': reviews, 'last_prose': last_prose}


def require_current_ceiling(connection, job):
    require_agent(connection, job['step'])
    reader = job.get('reader')
    for lens in (reader or {}).get('lenses') or []:
        require_agent(connection, lens_task(lens))


def next_jobs(connection, run, jobs):
    state = progress(run, jobs)
    require(state['status'] == 'ready', 'Finish or explicitly retry this recipe step before preparing the next one.', 409)
    result = []
    for template in run['snapshot']['plan'][state['stage']]['templates']:
        require_current_ceiling(connection, template)
        job = compile_job(run['snapshot'], template, state['draft'], state['reviews'], run['chance'])
        result.append(bind_job(job, run['bindings']))
    return {'stage': state['stage'], 'jobs': result}


def step_preview(connection, run, jobs):
    prepared = next_jobs(connection, run, jobs)
    return {**prepared, 'revision': run['revision'], 'preview_hash': snapshot_hash(prepared),
            'request_count': len(prepared['jobs']), 'provider_cost': None}
