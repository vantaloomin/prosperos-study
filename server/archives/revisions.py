from server.archives.source_memory import validate_scene_projection
from server.database import decode, one
from server.errors import require
from server.memory.control_packet import with_decisions
from server.scenes.models import SceneState
from server.scenes.output import parse_scene
from server.scenes.revision_context import triage_context, triage_inputs, verification_inputs
from server.scenes.revision_decisions import package_items, resolved_triage
from server.scenes.revision_models import validate_triage
from server.scenes.state import run_record, selected_result, upstream


def validate_revision_job(connection, job):
    snapshot = decode(job['snapshot'])
    origin = run_record(connection, job['run_id'])
    frozen = {**origin, 'state': SceneState.model_validate(snapshot['upstream']).model_dump()}
    if job['step'] == 'scene-triage':
        expected = triage_inputs(connection, frozen, snapshot['review_job_ids'])
    else:
        require(not snapshot['review_job_ids'], 'A verification job cannot replace its triage reports.')
        expected = verification_inputs(connection, frozen, snapshot['item_id'])
    expected = with_decisions(expected, frozen['snapshot'])
    validate_scene_projection(connection, frozen['snapshot'], expected, snapshot)
    if job['status'] == 'done':
        require(parse_scene(job['output'], snapshot) == decode(job['result']), 'A revision result disagrees with its preserved output.')


def validate_verifications(connection, run):
    items = (selected_result(connection, run, 'scene-triage') or {}).get('items', [])
    ids = {item['id'] for item in items}
    require(set(run['state']['verifications']) <= ids, 'A verdict refers to an unknown triage item.')
    require(set(run['state']['triage_edits']) <= ids, 'A director resolution refers to an unknown triage item.')
    for item_id, job_id in run['state']['verifications'].items():
        job = one(connection, 'SELECT * FROM scene_jobs WHERE id=?', (job_id,))
        snapshot = decode(job['snapshot'])
        require(job['run_id'] == run['id'] and job['step'] == 'scene-verify' and job['status'] == 'done',
                'A saved verdict must be a completed verification from this scene.')
        require(snapshot['upstream'] == upstream(run, 'scene-verify') and snapshot['item_id'] == item_id,
                'A saved verdict belongs to a different triage item or draft.')


def validate_package(connection, run):
    result = resolved_triage(connection, run)
    gate = run['state']['gate_b']
    require(not gate or result, 'A revision approval has no triage result.')
    if not result:
        return
    context = triage_context(connection, run)
    validate_triage(result, context)
    if not gate:
        return
    require(result['approach'] == 'patch' and all(item['disposition'] != 'verify' for item in result['items']),
            'An approved package has unresolved findings or needs redrafting.')
    requested = gate['item_ids'] if gate['package'] == 'custom' else []
    require(gate['package'] in {'A', 'B', 'C', 'custom'}, 'Unsupported revision package.')
    chosen = package_items(result, context, gate['package'], requested)
    require(chosen == gate['items'] and [item['id'] for item in chosen] == gate['item_ids'], 'Approved changes disagree with the saved package.')
    require(set(gate['confirmed_hold_ids']) == {item['id'] for item in chosen if item['disposition'] == 'hold'},
            'A structural change lacks explicit director confirmation.')
    require(gate['triage_job_id'] == run['state']['selections']['scene-triage'] and gate['approved_at'],
            'Revision approval belongs to another triage result.')


def validate_revisions(connection, document):
    for job in document['data']['scene_jobs']:
        if job['step'] in {'scene-triage', 'scene-verify'}:
            validate_revision_job(connection, job)
    for row in document['data']['scene_runs']:
        run = run_record(connection, row['id'])
        validate_verifications(connection, run)
        validate_package(connection, run)
