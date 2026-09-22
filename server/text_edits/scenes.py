from server.database import decode, one
from server.errors import require
from server.phrases.detection import digest
from server.scenes.author_text import selected_draft, source_block
from server.scenes.catalog import PLAN_KEYS
from server.scenes.state import run_record, save_decision
from server.text_edits.models import TextTarget
from server.text_edits.targets import snapshot


def source_scene(connection, ref):
    run = run_record(connection, ref.scene_id)
    require(run['branch_id'] == ref.branch_id and run['snapshot']['branch']['story_id'] == ref.story_id,
            'This scene text belongs to another Story or telling.', 409)
    job, original = source_block(connection, ref)
    require(run['state']['selections'].get(job['step']) == ref.job_id,
            'Another scene result is selected. Open its own text target to revise it.', 409)
    draft = selected_draft(connection, run)
    require(draft and draft['complete'], 'Complete the scene draft and its dialogue before editing its text.', 409)
    return run, original, draft


def scene_snapshot(connection, ref):
    run, original, draft = source_scene(connection, ref)
    block = next((item for item in draft['blocks'] if item['id'] == ref.item_id), None)
    require(block is not None, 'This block is outside the selected scene draft.', 409)
    return block_snapshot(run, ref, original, block)


def block_snapshot(run, ref, original, block):
    edit = run['state'].get('draft_edits', {}).get(ref.item_id)
    basis = {'revision': run['revision'], 'original_sha256': digest(original),
             'edit_receipt_id': edit['receipt_id'] if edit else None}
    return snapshot(ref, basis, block['text'], f"{run['title']} · {block.get('speaker') or 'Prose'} · {ref.item_id}", 100000)


def require_scene_editable(connection, ref):
    run, _, _ = source_scene(connection, ref)
    require(not run['state']['accepted'], 'This scene was kept. Revise its accepted passage from the Story.', 409)
    require(run['state']['gate_a'], 'Approve the scene plan before editing its draft.', 409)
    return run


def publish_scene_block(connection, ref, text, receipt_id):
    run = require_scene_editable(connection, ref)
    state = run['state']
    state.setdefault('draft_edits', {})[ref.item_id] = {'text': text, 'receipt_id': receipt_id, 'job_id': ref.job_id}
    draft = selected_draft(connection, run)
    require(len(draft['text']) <= 100000, 'The completed scene exceeds 100,000 characters.')
    # Preserve planning and original drafting results. Every derived judgement is stale.
    state['selections'] = {key: value for key, value in state['selections'].items() if key in PLAN_KEYS + ['scene-draft', 'scene-dialogue']}
    state.update(triage_edits={}, verifications={}, gate_b=None, patch_round=0, repair_selections={})
    save_decision(connection, run, 'text-edit', {'step': 'scene-draft', 'receipt_id': receipt_id, 'job_id': ref.job_id, 'item_id': ref.item_id}, state)
    return ref, {'scene_id': run['id'], 'job_id': ref.job_id, 'item_id': ref.item_id}


def scene_text_targets(connection, run, draft):
    if not draft or not draft['complete']:
        return []
    result, originals = [], {}
    for step, key, identity in (('scene-draft', 'blocks', 'id'), ('scene-dialogue', 'lines', 'slot_id')):
        job_id = run['state']['selections'].get(step)
        if job_id:
            source = decode(one(connection, 'SELECT result FROM scene_jobs WHERE id=?', (job_id,))['result'])
            originals.update({item[identity]: item['text'] for item in source[key] if 'text' in item})
    for block in draft['blocks']:
        step = 'scene-dialogue' if block['kind'] == 'dialogue' else 'scene-draft'
        ref = TextTarget(kind='scene-block', story_id=run['snapshot']['branch']['story_id'], branch_id=run['branch_id'],
                         scene_id=run['id'], job_id=run['state']['selections'][step], item_id=block['id'])
        result.append(block_snapshot(run, ref, originals[block['id']], block))
    return result
