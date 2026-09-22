"""Author wording retains draft structure and never mutates specialist output."""
from server.database import decode, one
from server.errors import require
from server.scenes.drafts import assemble_draft
from server.scenes.state import selected_result


def selected_draft(connection, run):
    source = selected_result(connection, run, 'scene-draft')
    if not source:
        return None
    result = assemble_draft(source, selected_result(connection, run, 'scene-dialogue'))
    edits = run['state'].get('draft_edits', {})
    if not edits:
        return result
    require(result['complete'], 'Author wording needs a complete selected scene draft.', 409)
    result['blocks'] = [{**block, 'text': edits[block['id']]['text']} if block['id'] in edits else block for block in result['blocks']]
    result['text'] = '\n\n'.join(block['text'] for block in result['blocks'])
    result['proposed_facts'] = []
    return result


def source_block(connection, ref):
    job = one(connection, 'SELECT * FROM scene_jobs WHERE id=?', (ref.job_id,))
    require(job['run_id'] == ref.scene_id and job['status'] == 'done' and job['step'] in {'scene-draft', 'scene-dialogue'},
            'This text target is not a completed draft or dialogue result from this scene.', 409)
    result = decode(job['result'])
    key, identity = ('blocks', 'id') if job['step'] == 'scene-draft' else ('lines', 'slot_id')
    block = next((item for item in result[key] if item[identity] == ref.item_id), None)
    require(block and 'text' in block, 'This scene text block is missing or still awaiting dialogue.', 409)
    return job, block['text']
