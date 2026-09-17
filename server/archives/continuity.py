from server.archives.manual_scenes import validate_manual_scene
from server.archives.patches import validate_repair
from server.archives.revisions import validate_package, validate_verifications
from server.continuity import continuity_view
from server.database import decode, many, one
from server.errors import require
from server.scenes.acceptance import acceptance_material
from server.scenes.continuity_context import continuity_inputs
from server.scenes.continuity_models import SceneAcceptance
from server.scenes.models import SceneState
from server.scenes.output import parse_scene
from server.scenes.state import require_step, run_record


def entry_values(entries):
    return [{key: item[key] for key in ('id', 'kind', 'subject', 'text', 'status')} for item in entries]


def validate_proposal_job(connection, job):
    snapshot = decode(job['snapshot'])
    origin = run_record(connection, job['run_id'])
    frozen = {**origin, 'state': SceneState.model_validate(snapshot['upstream']).model_dump()}
    validate_verifications(connection, frozen)
    validate_package(connection, frozen)
    validate_repair(connection, frozen)
    require_step(frozen, job['step'])
    require(decode(snapshot['content']) == continuity_inputs(connection, frozen), 'A continuity proposal has altered frozen inputs.')
    if job['status'] == 'done':
        require(parse_scene(job['output'], snapshot) == decode(job['result']), 'A continuity proposal differs from its preserved output.')


def validate_commit(connection, row):
    run = run_record(connection, row['scene_id'])
    receipt = run['state']['accepted']
    require(receipt and all(receipt[key] == row[key] for key in ('branch_id', 'node_id', 'proposal_job_id'))
            and receipt['commit_id'] == row['id'], 'An accepted scene and continuity receipt disagree.')
    require(receipt['proposal_job_id'] == run['state']['selections'].get('scene-continuity'), 'Acceptance used an unselected proposal.')
    body = SceneAcceptance(operation_id='archive-validation', expected_revision=run['revision'],
                           selected_ids=receipt['selected_ids'], include_summary=receipt['include_summary'])
    text, changes, summary = acceptance_material(connection, run, body)
    require(changes == decode(row['changes']) and summary == row['summary'], 'Accepted continuity differs from the approved selection.')
    node = one(connection, 'SELECT * FROM nodes WHERE id=?', (row['node_id'],))
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
    original = run['snapshot']['branch']
    require(node['parent_id'] == original['head_id'] and node['manifest_id'] == original['manifest_id'] and node['text'] == text,
            'Accepted scene text or its starting point changed.')
    require(node['story_id'] == branch['story_id'] == original['story_id'], 'A continuity commit crosses Stories.')
    require(node['role'] == 'assistant', 'Accepted scene prose must be a narration response.')
    require(decode(node['metadata']) == {'source': 'accepted_scene', 'scene_id': run['id'], 'commit_id': row['id']},
            'Accepted prose has inconsistent scene provenance.')
    prior = continuity_view(connection, node['parent_id'])
    require(entry_values(prior['entries']) == entry_values(run['snapshot'].get('continuity', {}).get('entries', [])),
            'A scene used continuity outside its original accepted path.')
    validate_receipt_journal(connection, run, row)
    validate_acceptance_branch(connection, branch, row)


def validate_acceptance_branch(connection, branch, row):
    found = connection.execute('WITH RECURSIVE path AS (SELECT id,parent_id FROM nodes WHERE id=? '
        'UNION ALL SELECT n.id,n.parent_id FROM nodes n JOIN path p ON n.id=p.parent_id) '
        'SELECT 1 FROM path WHERE id=?', (branch['head_id'], row['node_id'])).fetchone()
    require(found is not None, 'The acceptance receipt points to a branch without its accepted scene.')


def validate_accepted_nodes(document):
    commits = {row['node_id']: row for row in document['data']['continuity_commits']}
    origins = set()
    for node in document['data']['nodes']:
        if decode(node['metadata']).get('source') == 'manual_scene':
            validate_manual_node(document, node)
        if decode(node['metadata']).get('source') != 'accepted_scene':
            continue
        require(node['id'] in commits, 'Accepted scene prose has no continuity receipt.')
        origin = (node['story_id'], commits[node['id']]['origin_id'])
        require(origin not in origins, 'A Story has duplicate continuity identities.')
        origins.add(origin)


def validate_receipt_journal(connection, run, row):
    decisions = many(connection, "SELECT * FROM scene_decisions WHERE run_id=? AND kind='accept'", (run['id'],))
    require(len(decisions) == 1 and decisions[0]['revision'] == run['revision'], 'Acceptance must be the final, unique scene decision.')
    payload = decode(decisions[0]['payload'])
    receipt = run['state']['accepted']
    require(payload['selected_ids'] == receipt['selected_ids'] and payload['include_summary'] == receipt['include_summary']
            and payload['note'] == row['note'], 'Acceptance and the director journal disagree.')
    require(len(row['origin_id']) == 32 and all(char in '0123456789abcdef' for char in row['origin_id']), 'Invalid continuity identity.')


def validate_continuity(connection, document):
    validate_accepted_nodes(document)
    for job in document['data']['scene_jobs']:
        if job['step'] == 'scene-continuity':
            validate_proposal_job(connection, job)
    for row in document['data']['continuity_commits']:
        validate_commit(connection, row)
    for row in document['data']['scene_runs']:
        run = run_record(connection, row['id'])
        receipt = run['state']['accepted']
        if receipt and receipt.get('manual_review'):
            validate_manual_scene(connection, run)
        elif receipt:
            commit = one(connection, 'SELECT scene_id FROM continuity_commits WHERE id=?', (receipt['commit_id'],))
            require(commit['scene_id'] == row['id'], 'An accepted scene has no matching commit.')


def validate_manual_node(document, node):
    metadata = decode(node['metadata'])
    scene = next((row for row in document['data']['scene_runs'] if row['id'] == metadata.get('scene_id')), None)
    receipt = decode(scene['state']).get('accepted') if scene else None
    require(receipt and receipt.get('manual_review') is True and receipt.get('node_id') == node['id'],
            'Manually accepted prose has no matching director receipt.')
