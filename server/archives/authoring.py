from server.archives.records import related_rows
from server.authoring.catalog import AUTHORING_KEYS
from server.authoring.context import parse_authoring
from server.authoring.models import AuthoringPreview
from server.character_content import canonical_kind
from server.database import decode, many, one
from server.errors import require


def collect_authoring(connection, data, complete):
    data['authoring_runs'] = (many(connection, 'SELECT * FROM authoring_runs ORDER BY rowid') if complete else
        related_rows(connection, 'authoring_runs', 'asset_id', {row['id'] for row in data['assets']}))
    for table, field, parent in [('authoring_jobs', 'run_id', 'authoring_runs'), ('authoring_attempts', 'job_id', 'authoring_jobs')]:
        data[table] = related_rows(connection, table, field, {row['id'] for row in data[parent]})


def validate_authoring(connection, document):
    data = document['data']
    require(set(document['authoring_profiles']) <= AUTHORING_KEYS, 'Invalid Library assistant defaults.')
    for profile_id in document['authoring_profiles'].values():
        one(connection, 'SELECT id FROM profiles WHERE id=?', (profile_id,))
    runs = {row['id']: validate_run(connection, row) for row in data['authoring_runs']}
    jobs = {row['id']: row for row in data['authoring_jobs']}
    for job in jobs.values():
        snapshot = decode(job['snapshot'])
        run = runs[job['run_id']]
        require(job['step'] == snapshot['step'] == run['step'] and snapshot['prompt']['key'] == job['step'], 'Invalid authoring role.')
        require(snapshot['content'] == run['content'], 'Authoring comparisons must use the same frozen draft.')
        validate_configuration(connection, snapshot)
        validate_output(job, snapshot)
    for attempt in data['authoring_attempts']:
        validate_output(attempt, decode(jobs[attempt['job_id']]['snapshot']))


def validate_run(connection, row):
    run = decode(row['snapshot'])
    require(run['asset_id'] == row['asset_id'] and run['source_version_id'] == row['source_version_id'], 'Invalid authoring source.')
    require(bool(row['asset_id']) == bool(row['source_version_id']), 'Authoring needs both source identifiers or neither.')
    if row['source_version_id']:
        source = one(connection, 'SELECT v.asset_id,a.kind FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE v.id=?', (row['source_version_id'],))
        require(source['asset_id'] == row['asset_id'] and canonical_kind(source['kind']) == canonical_kind(run['kind']), 'Authoring source ownership differs.')
    content = decode(run['content'])
    require(content['kind'] == run['kind'] and content['name'] == run['name'] and content['target']['key'] == run['target_key'], 'Authoring target differs from its request.')
    body = AuthoringPreview.model_validate({key: run[key] for key in ('source_version_id', 'draft_id', 'kind', 'name', 'target_key', 'step')} | {
        'target_label': content['target']['label'], 'text': content['target']['text'], 'context': content['supporting_fields'], 'direction': content['direction']})
    if run['step'] == 'authoring-enrich':
        from server.memory.enrichment import validate_request
        validate_request(body)
    return run


def validate_output(row, snapshot):
    require(row['status'] in {'queued', 'running', 'done', 'error', 'cancelled', 'interrupted'}, 'Invalid authoring status.')
    if row['status'] == 'done':
        require(decode(row['result']) == parse_authoring(row['output'], snapshot), 'Authoring proposal differs from its validated output.')


def validate_configuration(connection, snapshot):
    profile = snapshot['profile']
    version = one(connection, 'SELECT * FROM profile_versions WHERE id=?', (profile['id'],))
    require(version['profile_id'] == profile['profile_id'] and decode(version['config']) == profile['config'], 'Authoring profile differs from its saved version.')
    prompt = snapshot['prompt']
    version = one(connection, 'SELECT * FROM prompt_versions WHERE id=?', (prompt['id'],))
    require(version['key'] == prompt['key'] and version['template'] == prompt['template'], 'Authoring instructions differ from their saved version.')
