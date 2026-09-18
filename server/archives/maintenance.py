from server.branches import path_nodes
from server.database import decode, many, one
from server.errors import require


def validate_maintenance(connection, data):
    wakes = {row['branch_id']: row for row in data['summary_wakeups']}
    for row in wakes.values():
        require(row['status'] in {'pending', 'idle', 'limited', 'paused', 'error', 'interrupted'} and row['revision'] >= 1,
                'Invalid automatic maintenance state.')
    paths = {}
    for row in data['summary_pending']:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
        if branch['id'] not in paths:
            paths[branch['id']] = {node['id']: node for node in path_nodes(connection, branch['head_id'])}
        nodes = paths[branch['id']]
        require(branch['id'] in wakes and row['node_id'] in nodes and nodes[row['node_id']]['role'] != 'ooc',
                'Pending maintenance refers to untracked, unrelated or non-prose history.')
    for batch in data['summary_batches']:
        validate_batch(connection, batch)


def validate_batch(connection, batch):
    require(batch['status'] in {'queued', 'running', 'done', 'error', 'cancelled', 'paused', 'interrupted'}, 'Invalid summary batch status.')
    snapshot = decode(batch['snapshot'])
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (batch['branch_id'],))
    require(snapshot['branch']['id'] == branch['id'] and snapshot['branch']['story_id'] == branch['story_id'], 'Summary batch crosses Stories.')
    require(type(snapshot['batch_size']) is int and 1 <= snapshot['batch_size'] <= 8
            and type(snapshot['max_batches']) is int and 1 <= snapshot['max_batches'] <= 4, 'Invalid summary batch limits.')
    runs = many(connection, 'SELECT r.snapshot,l.ordinal,r.id FROM summary_runs r JOIN summary_batch_runs l ON l.run_id=r.id '
                'WHERE l.batch_id=? ORDER BY l.ordinal', (batch['id'],))
    require(1 <= len(runs) <= snapshot['max_batches'] and [row['ordinal'] for row in runs] == list(range(len(runs))), 'Invalid summary batch order.')
    selected, requests, seen, profiles = 0, 0, set(), None
    for row in runs:
        run = decode(row['snapshot'])
        require(run['branch'] == snapshot['branch'] and run['story_revision'] == snapshot['story_revision'], 'Summary batch inputs disagree with their boundary.')
        links = run['source_links']
        require(1 <= len(links) <= snapshot['batch_size'], 'A summary batch exceeds its excerpt allowance.')
        validate_distinct_ranges(links, seen)
        jobs = many(connection, 'SELECT * FROM summary_jobs WHERE run_id=? ORDER BY rowid', (row['id'],))
        profiles = validate_jobs(batch, jobs, profiles)
        selected += len(links)
        requests += len(jobs)
    require(selected == snapshot['selected_count'] <= snapshot['eligible_count'] and requests == snapshot['request_count'], 'Summary batch counts are inconsistent.')


def validate_jobs(batch, jobs, profiles):
    require(1 <= len(jobs) <= 4, 'A summary batch needs 1 to 4 profiles per group.')
    if batch['kind'] == 'automatic':
        require(len(jobs) == 1, 'Automatic summary batches use one saved step profile.')
    current = [(decode(job['snapshot'])['profile']['id'], decode(job['snapshot'])['prompt']['id']) for job in jobs]
    require(profiles is None or current == profiles, 'Summary batch groups have different model or instruction versions.')
    if batch['status'] == 'done':
        require(all(job['status'] == 'done' for job in jobs), 'A finished summary batch contains unfinished work.')
    return current


def validate_distinct_ranges(links, seen):
    for link in links:
        key = (link['node_id'], link['start'], link['end'])
        require(key not in seen, 'A summary batch repeats a source range.')
        seen.add(key)
