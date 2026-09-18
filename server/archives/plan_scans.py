"""Bind optional plan review suggestions to their frozen branch and original prose."""
from server.database import decode, many
from server.errors import require
from server.memory.plan_edits import plan_sources
from server.memory.plan_scan import PURPOSE, eligible_plans, plan_context, reviewed_sources
from server.memory.plan_scan_output import parse_plan_scan


def validate_scan_job(connection, run, job, sources, plans):
    snapshot = decode(job['snapshot'])
    require(job['step'] == snapshot['step'] == 'scene-continuity' and snapshot.get('purpose') == PURPOSE,
            'A plan review changed its role.')
    context = decode(snapshot['content'])
    selected = [entry['id'] for entry in context['existing_entries']]
    require(len(selected) == len(set(selected)) and set(selected) <= plans.keys(), 'A plan review included foreign or duplicate plans.')
    expected = plan_context(sources, [plans[key] for key in selected], len(plans) - len(selected))
    require(context == expected, 'A plan review changed its frozen passages or established plans.')
    if job['status'] == 'done':
        require(parse_plan_scan(job['output'], snapshot) == decode(job['result']),
                'Saved plan suggestions differ from their validated output.')
    for attempt in many(connection, 'SELECT * FROM review_attempts WHERE job_id=?', (job['id'],)):
        if attempt['status'] == 'done':
            require(parse_plan_scan(attempt['output'], snapshot) == decode(attempt['result']),
                    'Saved plan suggestion attempts differ from their original output.')


def validate_plan_scan(connection, row, run):
    require(run['branch']['id'] == row['branch_id'] and not run.get('scene'), 'A plan review crosses branches or scene workflows.')
    all_sources = list(plan_sources(connection, run['branch']['head_id']))
    positions = {source['id']: index for index, source in enumerate(all_sources)}
    ids = run['scan_source_ids']
    require(1 <= len(ids) <= 8 and len(ids) == len(set(ids)) and set(ids) <= positions.keys(),
            'A plan review has invalid accepted passages.')
    selected = [all_sources[positions[source_id]] for source_id in ids]
    seen = run.get('reviewed_source_ids', [])
    require(len(seen) == len(set(seen)) and set(seen) <= positions.keys()
            and set(seen) <= reviewed_sources(connection, row['branch_id']),
            'A plan review claimed unrecorded prior coverage.')
    require([positions[source_id] for source_id in ids] == sorted(positions[source_id] for source_id in ids)
            and run['remaining_passages'] == len(positions.keys() - set(seen) - set(ids)),
            'A plan review changed its passage order or coverage.')
    plans = {entry['id']: entry for entry in eligible_plans(connection, run['branch'], run.get('continuity_version_id'))}
    jobs = many(connection, 'SELECT * FROM review_jobs WHERE run_id=?', (row['id'],))
    require(1 <= len(jobs) <= 4, 'A plan review needs one to four saved requests.')
    for job in jobs:
        validate_scan_job(connection, run, job, selected, plans)
