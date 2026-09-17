"""Explicit director acceptance when automated agents have been disabled."""
from server.branches import insert_node, touch_branch
from server.errors import require
from server.generations import Generations
from server.scenes.chance import scene_mechanics_state
from server.scenes.context import draft_view
from server.scenes.patch_context import patch_view
from server.scenes.switches import manual_steps


def manual_material(connection, run):
    if not manual_steps(run) or not run['state']['gate_a']:
        return None
    draft = draft_view(connection, run)
    if not draft or not draft['complete']:
        return None
    patch = patch_view(connection, run)
    # Never silently discard selected edits, including partially finished revisions.
    return {'text': patch['text'] if patch else draft['text'],
            'source': 'Selected revised prose' if patch else 'Selected scene draft',
            'disabled_steps': manual_steps(run)}


def accept_manually(connection, run, body):
    material = manual_material(connection, run)
    require(material, 'Complete the selected draft before manually accepting a scene with disabled agents.', 409)
    require(not body.selected_ids and not body.include_summary, 'Manual acceptance cannot commit generated continuity.')
    target = Generations._accept_branch(connection, run['snapshot']['branch'], run['snapshot'], body)
    metadata = {'source': 'manual_scene', 'scene_id': run['id'], 'disabled_steps': material['disabled_steps']}
    node_id = insert_node(connection, target, material['text'], 'assistant', metadata, scene_mechanics_state(run))
    touch_branch(connection, target['id'], node_id)
    state = run['state']
    state['accepted'] = {'manual_review': True, 'branch_id': target['id'], 'node_id': node_id,
                         'disabled_steps': material['disabled_steps'], 'selected_ids': [], 'include_summary': False}
    return state
