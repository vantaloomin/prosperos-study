from server.archives.revisions import validate_package, validate_verifications
from server.archives.scenes import selected_jobs
from server.archives.source_memory import validate_scene_projection
from server.database import decode, one
from server.errors import require
from server.memory.control_packet import with_decisions
from server.scenes.models import SceneState
from server.scenes.output import parse_scene
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.patch_context import patch_inputs, patch_keys
from server.scenes.patch_validation import patch_check_passes
from server.scenes.state import require_step, run_record, upstream


def validate_patch_job(connection, job):
    snapshot = decode(job['snapshot'])
    origin = run_record(connection, job['run_id'])
    frozen = {**origin, 'state': SceneState.model_validate(snapshot['upstream']).model_dump()}
    validate_verifications(connection, frozen)
    validate_package(connection, frozen)
    validate_repair(connection, frozen)
    require_step(frozen, job['step'])
    content = decode(snapshot['content'])
    validate_scene_projection(connection, frozen['snapshot'],
                              with_decisions(patch_inputs(connection, frozen, job['step'], content.get('context_version', 0)), frozen['snapshot']), snapshot)
    if job['status'] == 'done':
        require(parse_scene(job['output'], snapshot) == decode(job['result']), 'A patch result disagrees with its preserved output.')


def validate_repair(connection, run):
    state = run['state']
    repair = state['repair_selections']
    if not state['patch_round']:
        require(not repair, 'Correction references exist before a correction round.')
        return
    require(set(repair) == set(patch_keys(run)), 'A correction needs the entire previously checked patch.')
    selected_jobs(connection, run['id'], repair)
    old_state = {**state, 'patch_round': 0, 'repair_selections': {},
                 'selections': {**{key: value for key, value in state['selections'].items() if key not in PATCH_KEYS}, **repair}}
    previous = {**run, 'state': old_state}
    for key, job_id in repair.items():
        job = one(connection, 'SELECT snapshot,result FROM scene_jobs WHERE id=?', (job_id,))
        require(decode(job['snapshot'])['upstream'] == upstream(previous, key), 'A correction refers to a different approved package or patch round.')
    check = one(connection, 'SELECT result FROM scene_jobs WHERE id=?', (repair['scene-patch-check'],))
    require(not patch_check_passes(decode(check['result'])), 'A correction needs a failed check.')


def validate_patches(connection, document):
    for job in document['data']['scene_jobs']:
        if job['step'] in PATCH_KEYS:
            validate_patch_job(connection, job)
    for row in document['data']['scene_runs']:
        run = run_record(connection, row['id'])
        validate_repair(connection, run)
        for key in set(run['state']['selections']) & set(PATCH_KEYS):
            require_step(run, key)
