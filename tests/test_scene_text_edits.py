import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import V44_TABLES
from server.database import decode
from tests.test_agent_switches import skipped_scene
from tests.test_archives import backup, restore
from tests.test_consolidated_scene import drafted_scene, scene_readers, selected
from tests.test_scene_continuity import acceptance_body, ready_continuity
from tests.test_scene_drafting import LINE, PROSE, approved_plan
from tests.test_scene_reviews import reviewable_plan
from tests.test_scenes import choose, decide, get_plan, run_stage
from tests.test_text_edits import apply, proposal, undo


def source(client, scene_id, block=0):
    return get_plan(client, scene_id)['text_targets'][block]


def change(client, scene_id, text, block=0):
    return apply(client, proposal(client, source(client, scene_id, block), text))


def test_scene_text_preserves_structure_original_jobs_plan_and_independent_blocks(client, story):
    scene_id, provider = reviewable_plan(client, story, dialogue=True)
    before = get_plan(client, scene_id)
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    count = len(provider.calls)
    first = change(client, scene_id, '  The author’s prose 🦉.\n')
    after = get_plan(client, scene_id)
    assert after['draft']['text'] == '  The author’s prose 🦉.\n\n\n' + LINE
    assert after['draft']['blocks'][1] == before['draft']['blocks'][1]
    assert after['state']['gate_a'] == before['state']['gate_a']
    assert after['draft']['proposed_facts'] == [] and not after['coverage_passes']
    assert after['state']['selections'] == {key: value for key, value in before['state']['selections'].items() if key != 'scene-coverage'}
    assert [{key: job[key] for key in ('id', 'snapshot', 'output', 'result', 'usage')} for job in after['jobs']] == [
        {key: job[key] for key in ('id', 'snapshot', 'output', 'result', 'usage')} for job in before['jobs']]
    assert client.get(f"/api/branches/{story['branch_id']}").json() == branch and len(provider.calls) == count
    change(client, scene_id, 'An independently revised line.', 1)
    restored = undo(client, first)['receipt']
    assert restored['after_target']['text'] == PROSE
    assert get_plan(client, scene_id)['draft']['text'] == PROSE + '\n\nAn independently revised line.'
    assert not get_plan(client, scene_id)['coverage_passes']


def test_stale_scene_proposals_and_same_block_undo_do_not_overwrite(client, story):
    scene_id, _ = drafted_scene(client, story)
    pending = proposal(client, source(client, scene_id), 'Pending words.')
    first = change(client, scene_id, 'Independent words.')
    response = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': pending['revision']})
    assert response.status_code == 409
    change(client, scene_id, 'Newest words.')
    assert undo(client, first)['status'] == 'conflict'
    assert get_plan(client, scene_id)['draft']['blocks'][0]['text'] == 'Newest words.'


def test_scene_edit_clears_patch_and_continuity_gates_and_requires_new_review(client, story):
    scene_id, _ = ready_continuity(client, story, dialogue=True)
    before = get_plan(client, scene_id)
    change(client, scene_id, PROSE + ' The author checks the latch.')
    after = get_plan(client, scene_id)
    assert not after['patch'] and not after['continuity_proposal'] and not after['state']['gate_b']
    assert not after['state']['triage_edits'] and not after['state']['verifications'] and not after['state']['repair_selections']
    assert after['state']['patch_round'] == 0 and not after['coverage_passes']
    assert len(after['jobs']) == len(before['jobs'])
    response = client.post(f'/api/scenes/{scene_id}/accept', json=acceptance_body(client, scene_id))
    assert response.status_code == 409
    prior = next(job for job in before['jobs'] if job['id'] == before['state']['selections']['scene-coverage'])
    response = client.post(f'/api/scenes/{scene_id}/choose', json={'operation_id': uuid4().hex, 'expected_revision': after['revision'], 'job_id': prior['id']})
    assert response.status_code == 409
    file, _ = backup(client, story)
    restore(client, file)


def test_current_review_and_patch_inputs_use_author_words_and_restore_after_later_edits(client, story):
    scene_id, provider = drafted_scene(client, story)
    old_review = scene_readers(client, story, scene_id)
    prose = 'The author sees a sealed letter, still waiting on the desk.'
    receipt = change(client, scene_id, prose)
    assert not get_plan(client, scene_id)['coverage_passes']
    old = client.post(f'/api/scenes/{scene_id}/preview', json={'expected_revision': get_plan(client, scene_id)['revision'], 'key': 'scene-triage', 'review_job_ids': [job['id'] for job in old_review['jobs']]})
    assert old.status_code == 409
    new_review = scene_readers(client, story, scene_id)
    assert all(decode(job['snapshot']['content'])['sources'][0]['text'].startswith(prose) for job in new_review['jobs'])
    selected(client, scene_id, 'scene-triage', review_job_ids=[job['id'] for job in new_review['jobs']])
    decide(client, scene_id, 'approve-revision', {'package': 'B'})
    patch = selected(client, scene_id, 'scene-patch')
    assert decode(patch['snapshot']['content'])['blocks'][0]['text'] == prose
    change(client, scene_id, 'Later independent wording.')
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    restored = get_plan(client, mapping[scene_id])
    assert restored['draft']['blocks'][0]['text'] == 'Later independent wording.'
    assert not restored['patch']
    restored_patch = next(job for job in restored['jobs'] if job['id'] == mapping[patch['id']])
    assert restored_patch['snapshot']['content'] == patch['snapshot']['content']
    review_rows = {row['id']: row for row in document['data']['review_jobs']}
    second, again = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    assert all(decode(row['snapshot'])['content'] == decode(review_rows[old]['snapshot'])['content'] for row in again['data']['review_jobs'] for old, new in mapping.items() if row['id'] == new and old in review_rows)
    restore(client, second)
    assert receipt['id'] in mapping and provider.calls


def test_explicit_manual_keep_accepts_author_scene_and_refuses_later_draft_edits(client, story):
    scene_id, provider = skipped_scene(client, story)
    receipt = change(client, scene_id, '  Exact manually reviewed scene 🦉.\n')
    run = get_plan(client, scene_id)
    assert run['manual_acceptance']['text'] == receipt['after_target']['text']
    body = {'operation_id': uuid4().hex, 'expected_revision': run['revision'], 'manual_review': True}
    response = client.post(f'/api/scenes/{scene_id}/accept', json=body)
    assert response.status_code == 200, response.text
    assert client.post(f'/api/scenes/{scene_id}/accept', json=body).json() == response.json()
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == receipt['after_target']['text']
    assert len(provider.calls) == 1
    assert client.post(f"/api/text-edit-receipts/{receipt['id']}/undo", json={'operation_id': uuid4().hex}).status_code == 409
    file, _ = backup(client, story)
    restore(client, file)


def test_new_selected_specialist_preserves_receipts_and_rejects_old_target_undo(client, story):
    scene_id, _ = drafted_scene(client, story)
    receipt = change(client, scene_id, 'Author wording.')
    selected(client, scene_id, 'scene-draft')
    selected(client, scene_id, 'scene-dialogue')
    run = get_plan(client, scene_id)
    assert not run['state'].get('draft_edits') and 'Author wording.' not in run['draft']['text']
    assert client.post('/api/text-targets/read', json={'target': receipt['after_target']['ref']}).status_code == 409
    assert client.get(f"/api/text-edit-receipts/{receipt['id']}").status_code == 200
    assert client.post(f"/api/text-edit-receipts/{receipt['id']}/undo", json={'operation_id': uuid4().hex}).status_code == 409
    file, _ = backup(client, story)
    restore(client, file)


def test_incomplete_split_scene_cannot_be_edited_and_targets_cannot_cross_stories(client, story):
    scene_id, _ = approved_plan(client, story, dialogue=True)
    job = run_stage(client, scene_id, 'scene-draft')[0]
    choose(client, scene_id, job)
    ref = {'kind': 'scene-block', 'story_id': story['story_id'], 'branch_id': story['branch_id'], 'scene_id': scene_id, 'job_id': job['id'], 'item_id': 'p1'}
    assert not get_plan(client, scene_id)['text_targets']
    assert client.post('/api/text-targets/read', json={'target': ref}).status_code == 409
    choose(client, scene_id, run_stage(client, scene_id, 'scene-dialogue')[0])
    other = client.post('/api/stories', json={'title': 'Other'}).json()
    for changed in ({'story_id': other['story_id']}, {'branch_id': other['branch_id']}, {'item_id': 'missing'}):
        assert client.post('/api/text-targets/read', json={'target': {**ref, **changed}}).status_code == 409


def test_empty_scene_remains_unaccepted(client, story):
    scene_id, _ = skipped_scene(client, story)
    receipt = change(client, scene_id, '')
    run = get_plan(client, scene_id)
    assert run['draft']['complete'] and run['draft']['text'] == ''
    assert client.post(f'/api/scenes/{scene_id}/accept', json={'operation_id': uuid4().hex, 'expected_revision': run['revision'], 'manual_review': True}).status_code == 409
    undo(client, receipt)


def test_combined_scene_size_limit_preserves_other_blocks(client, story):
    scene_id, _ = drafted_scene(client, story)
    before = get_plan(client, scene_id)
    pending = proposal(client, source(client, scene_id), 'a' * 100000)
    response = client.post(f"/api/text-edits/{pending['id']}/apply", json={'operation_id': uuid4().hex, 'expected_revision': pending['revision']})
    assert response.status_code == 400
    assert get_plan(client, scene_id)['draft'] == before['draft']


def test_edited_scene_can_complete_fresh_review_and_normal_acceptance(client, story):
    scene_id, provider = drafted_scene(client, story)
    change(client, scene_id, 'The author checks the sealed letter, still waiting for an answer.')
    review = scene_readers(client, story, scene_id)
    selected(client, scene_id, 'scene-triage', review_job_ids=[job['id'] for job in review['jobs']])
    decide(client, scene_id, 'approve-revision', {'package': 'B'})
    selected(client, scene_id, 'scene-patch')
    selected(client, scene_id, 'scene-continuity')
    count = len(provider.calls)
    expected = get_plan(client, scene_id)['patch']['text']
    decide(client, scene_id, 'accept', {'selected_ids': [], 'include_summary': True})
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['text'] == expected
    assert len(provider.calls) == count
    file, _ = backup(client, story)
    restore(client, file)


def test_format44_upgrade_retains_original_scene_shape_and_rejects_new_text_targets(client, story):
    scene_id, _ = drafted_scene(client, story)
    _, document = backup(client, story)
    document['version'] = 44
    document['data'] = {key: document['data'][key] for key in V44_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 201
    assert 'draft_edits' not in decode(document['data']['scene_runs'][0]['state'])
    change(client, scene_id, 'An author revision from the newer format.')
    _, document = backup(client, story)
    document['version'] = 44
    document['data'] = {key: document['data'][key] for key in V44_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(document)}).status_code == 400


@pytest.mark.parametrize('damage', ['text', 'receipt', 'journal', 'source'])
def test_archive_refuses_tampered_scene_author_text_provenance(client, story, damage):
    scene_id, _ = drafted_scene(client, story)
    receipt = change(client, scene_id, 'Author wording.')
    _, document = backup(client, story)
    bad = deepcopy(document)
    row = bad['data']['scene_runs'][0]
    state = decode(row['state'])
    if damage == 'text':
        state['draft_edits']['p1']['text'] = 'Unreceipted words.'
    elif damage == 'receipt':
        state['draft_edits']['p1']['receipt_id'] = 'missing'
    elif damage == 'source':
        state['draft_edits']['p1']['job_id'] = state['selections']['scene-dialogue']
    else:
        decision = next(item for item in bad['data']['scene_decisions'] if item['kind'] == 'text-edit')
        decision['payload'] = json.dumps({**decode(decision['payload']), 'item_id': 'd1'})
    row['state'] = json.dumps(state)
    assert client.post('/api/archives/imports', json={'content': json.dumps(bad)}).status_code == 400
    assert receipt['after_target']['text'] == 'Author wording.'
