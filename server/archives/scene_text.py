from server.database import decode, many, one
from server.errors import require
from server.phrases.detection import digest
from server.scenes.author_text import selected_draft, source_block
from server.scenes.catalog import PLAN_KEYS
from server.scenes.state import run_record
from server.text_edits.models import TextTarget


def validate_scene_text_snapshot(connection, ref, value):
    run = run_record(connection, ref.scene_id)
    require(run['branch_id'] == ref.branch_id and run['snapshot']['branch']['story_id'] == ref.story_id,
            'A scene text edit crosses Stories or tellings.')
    _, original = source_block(connection, ref)
    basis = value['basis']
    require(set(basis) == {'revision', 'original_sha256', 'edit_receipt_id'} and 0 <= basis['revision'] <= run['revision'],
            'A scene text target has an invalid revision.')
    require(value['limit'] == 100000 and len(value['text']) <= 100000 and basis['original_sha256'] == digest(original),
            'A scene text target changed its original specialist output.')
    if not basis['edit_receipt_id']:
        require(value['text'] == original, 'An unedited scene text target differs from its original.')
        return
    saved = one(connection, 'SELECT after_target FROM text_edit_receipts WHERE id=?', (basis['edit_receipt_id'],))
    after = decode(saved['after_target'])
    require(after['ref'] == value['ref'] and after['text'] == value['text'] and after['basis']['revision'] <= basis['revision'],
            'A scene text target lost its author revision receipt.')


def validate_scene_text_result(connection, receipt):
    before, after = receipt['before_target'], receipt['after_target']
    require(before['ref'] == after['ref'] and after['basis'] == {**before['basis'], 'revision': before['basis']['revision'] + 1, 'edit_receipt_id': receipt['id']},
            'A scene text edit changed its destination or revision sequence.')
    ref = before['ref']
    result = {key: ref[key] for key in ('scene_id', 'job_id', 'item_id')}
    require(receipt['result'] == result, 'A scene text receipt changed its destination.')
    row = one(connection, 'SELECT kind,payload FROM scene_decisions WHERE run_id=? AND revision=?', (ref['scene_id'], after['basis']['revision']))
    require(row['kind'] == 'text-edit' and decode(row['payload']) == {'step': 'scene-draft', 'receipt_id': receipt['id'], 'job_id': ref['job_id'], 'item_id': ref['item_id']},
            'A scene text edit is missing its matching director decision.')


def validate_scene_author_state(connection, run_id, state):
    for block_id, edit in state.get('draft_edits', {}).items():
        receipt = one(connection, 'SELECT after_target FROM text_edit_receipts WHERE id=?', (edit['receipt_id'],))
        target = decode(receipt['after_target'])
        ref = TextTarget.model_validate(target['ref'])
        require(ref.kind == 'scene-block' and ref.scene_id == run_id and ref.item_id == block_id and ref.job_id == edit['job_id']
                and target['text'] == edit['text'], 'A scene author revision has invalid text or provenance.')
        job, _ = source_block(connection, ref)
        require(state['selections'].get(job['step']) == ref.job_id, 'A scene author revision belongs to another selected draft.')


def validate_scene_author_history(connection, run):
    edits = {}
    for row in many(connection, 'SELECT * FROM scene_decisions WHERE run_id=? AND revision<=? ORDER BY revision', (run['id'], run['revision'])):
        payload = decode(row['payload'])
        if row['kind'] == 'choose':
            job = one(connection, 'SELECT step FROM scene_jobs WHERE id=?', (payload['job_id'],))
            if job['step'] in PLAN_KEYS + ['scene-draft', 'scene-dialogue']:
                edits = {}
        elif row['kind'] == 'text-edit':
            receipt = one(connection, 'SELECT before_target,after_target FROM text_edit_receipts WHERE id=?', (payload['receipt_id'],))
            target = decode(receipt['after_target'])
            before = decode(receipt['before_target'])
            require(target['ref']['kind'] == 'scene-block' and target['ref']['scene_id'] == run['id'] and target['basis']['revision'] == row['revision'],
                    'A scene decision has the wrong text receipt.')
            require(before['basis']['edit_receipt_id'] == edits.get(payload['item_id'], {}).get('receipt_id'),
                    'A scene text edit skipped its previous author revision.')
            edits[payload['item_id']] = {'text': target['text'], 'receipt_id': payload['receipt_id'], 'job_id': payload['job_id']}
    require(edits == run['state'].get('draft_edits', {}), 'The current scene wording disagrees with its director journal.')
    validate_scene_author_state(connection, run['id'], run['state'])
    if edits:
        draft = selected_draft(connection, run)
        require(draft and draft['complete'] and len(draft['text']) <= 100000, 'The author scene text is incomplete or too long.')


def validate_frozen_scene_text(connection, data):
    for row in data['scene_jobs']:
        state = decode(row['snapshot'])['upstream']
        validate_scene_author_state(connection, row['run_id'], state)
    for row in data['review_runs']:
        scene = decode(row['snapshot']).get('scene')
        if scene:
            validate_scene_author_state(connection, scene['id'], scene['state'])
