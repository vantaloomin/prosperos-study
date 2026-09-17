from server.branches import insert_node, touch_branch
from server.database import encode, identifier, now
from server.errors import require
from server.generations import Generations
from server.scenes.chance import scene_mechanics_state
from server.scenes.context import stale_plan
from server.scenes.manual_acceptance import accept_manually
from server.scenes.patch_context import patch_view
from server.scenes.state import selected_result


def acceptance_material(connection, run, body):
    patch = patch_view(connection, run)
    proposal = selected_result(connection, run, 'scene-continuity')
    require(patch and patch['checked'] and proposal, 'Choose a continuity proposal for the checked scene before accepting.', 409)
    selected = set(body.selected_ids)
    require(len(selected) == len(body.selected_ids), 'Choose each continuity change once.')
    require(selected <= {item['id'] for item in proposal['changes']}, 'A selected continuity change is outside this proposal.')
    return patch['text'], [item for item in proposal['changes'] if item['id'] in selected], proposal['scene_summary'] if body.include_summary else ''


def accept_scene(connection, run, body):
    require(not run['state']['accepted'], 'This scene is already accepted. Open its recorded branch.', 409)
    require(not stale_plan(connection, run) or body.as_new_branch,
            'The Story changed. Accept on a new branch from the frozen scene starting point or start another scene.', 409)
    if body.manual_review:
        return accept_manually(connection, run, body)
    text, changes, summary = acceptance_material(connection, run, body)
    target = Generations._accept_branch(connection, run['snapshot']['branch'], run['snapshot'], body)
    commit_id = identifier()
    node_id = insert_node(connection, target, text, 'assistant', {'source': 'accepted_scene', 'scene_id': run['id'], 'commit_id': commit_id}, scene_mechanics_state(run))
    touch_branch(connection, target['id'], node_id)
    proposal_id = run['state']['selections']['scene-continuity']
    connection.execute('INSERT INTO continuity_commits VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (commit_id, commit_id, node_id, run['id'], proposal_id, target['id'], summary, encode(changes), body.note, now()))
    state = run['state']
    state['accepted'] = {'branch_id': target['id'], 'node_id': node_id, 'commit_id': commit_id,
                         'proposal_job_id': proposal_id, 'selected_ids': body.selected_ids, 'include_summary': body.include_summary}
    return state
