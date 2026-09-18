import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.database import decode, encode
from server.errors import DomainError
from server.providers.events import ProviderEvent
from server.scenes.patch_apply import apply_edits, passage_changes
from server.scenes.patch_validation import validate_patch, validate_patch_check
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile
from tests.test_scene_revisions import rejected_claim, triage_ready
from tests.test_scenes import choose, decide, finish_plan, get_plan, run_stage


class PatchProvider:
    """Saved test output only; production always uses the configured real adapter."""
    def __init__(self):
        self.corrupt = None
        self.fail_check = False

    async def generate(self, _profile, _prompt, content):
        result = patch_fixture(decode(content), self.fail_check)
        if self.corrupt:
            self.corrupt(result)
        yield ProviderEvent(text=encode(result), done=True)


def patch_fixture(context, fail=False):
    ids = [item['id'] for item in context['package']['items']]
    resolutions = [{'item_id': item, 'status': 'addressed', 'reason': 'Fixture: the player still chooses.'} for item in ids]
    if context['stage'] == 'scene-patch-check':
        return {'summary': 'UI/test fixture only: check of changed passages.', 'resolutions': resolutions,
                'checks': [{'change_id': change['id'], 'status': 'revise' if fail else 'pass',
                            'quotes': [change['after'] or change['before']], 'reason': 'Fixture assessment.'} for change in context['changes']], 'issues': []}
    kind = 'dialogue' if context['stage'] == 'scene-dialogue-patch' else 'prose'
    block = next(block for block in context['blocks'] if block['kind'] == kind)
    after = "'Shall we examine the seal?' Wren asks." if kind == 'dialogue' else 'Wren rests a hand beside the sealed letter, leaving the invitation open.'
    return {'summary': 'UI/test fixture only: explicit proposed patch.', 'resolutions': resolutions,
            'edits': [{'operation': 'replace', 'block_id': block['id'], 'before': block['text'], 'after': after,
                       'anchor_id': None, 'speaker': '', 'item_ids': ids, 'reason': 'Preserve the player’s open decision.'}]}


def ready_patch(client, story, dialogue=False):
    run_id, _, _ = triage_ready(client, story, dialogue)
    rejected_claim(client, run_id)
    decide(client, run_id, 'approve-revision', {'package': 'C', 'confirmed_hold_ids': ['t2']})
    provider = PatchProvider()
    client.app.state.scene_runner.provider = provider
    return run_id, provider


def selected_stage(client, run_id, key):
    job = run_stage(client, run_id, key)[0]
    assert job['status'] == 'done', job['error']
    choose(client, run_id, job)
    return job


def test_approved_patch_comparisons_preserve_original_and_story(client, story):
    run_id, _ = ready_patch(client, story)
    original = get_plan(client, run_id)
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    profiles = [make_profile(client, name)['profile_id'] for name in ('Patch A', 'Patch B')]
    jobs = run_stage(client, run_id, 'scene-patch', profiles)
    assert all(job['status'] == 'done' for job in jobs)
    assert jobs[0]['snapshot']['content'] == jobs[1]['snapshot']['content']
    choose(client, run_id, jobs[1])
    patched = get_plan(client, run_id)
    assert patched['state']['gate_b'] == original['state']['gate_b']
    assert patched['draft'] == original['draft'] and patched['patch']['text'] != original['draft']['text']
    assert patched['patch']['changes'][0]['before'] == original['draft']['blocks'][0]['text']
    check = selected_stage(client, run_id, 'scene-patch-check')
    inputs = decode(check['snapshot']['content'])
    assert 'blocks' not in inputs and 'draft' not in inputs
    assert inputs['changes'][0]['id'] == 'scene-patch:p1'
    assert get_plan(client, run_id)['patch']['checked']
    assert client.get(f"/api/branches/{story['branch_id']}").json() == branch


def test_split_patch_preserves_narration_and_dialogue_boundaries(client, story):
    run_id, provider = ready_patch(client, story, dialogue=True)
    original = get_plan(client, run_id)['draft']['blocks']
    assert preview(client, run_id, 'scene-dialogue-patch').status_code == 409
    selected_stage(client, run_id, 'scene-patch')
    first = get_plan(client, run_id)['patch']['blocks']
    assert first[1] == original[1] and first[0] != original[0]
    assert preview(client, run_id, 'scene-patch-check').status_code == 409
    provider.corrupt = lambda result: result['edits'][0].update(block_id='p1', before=first[0]['text'])
    invalid = run_stage(client, run_id, 'scene-dialogue-patch')[0]
    assert invalid['status'] == 'error' and 'other writer' in invalid['error']
    provider.corrupt = None
    assert client.post(f"/api/scene-jobs/{invalid['id']}/retry").status_code == 200
    retried = next(job for job in finish_plan(client, run_id)['jobs'] if job['id'] == invalid['id'])
    choose(client, run_id, retried)
    second = get_plan(client, run_id)['patch']['blocks']
    assert second[0] == first[0] and second[1]['speaker'] == first[1]['speaker']
    assert second[1]['text'] != first[1]['text']
    selected_stage(client, run_id, 'scene-patch-check')
    assert get_plan(client, run_id)['patch']['checked']


def preview(client, run_id, step):
    return client.post(f'/api/scenes/{run_id}/preview', json={'key': step, 'expected_revision': get_plan(client, run_id)['revision']})


@pytest.mark.parametrize('corruption', ['before', 'foreign', 'duplicate', 'unapproved-insert', 'all-cut', 'speaker'])
def test_invalid_patches_preserve_failed_output_without_selecting(client, story, corruption):
    run_id, provider = ready_patch(client, story)
    corruptions = {
        'before': lambda result: result['edits'][0].update(before='invented'),
        'foreign': lambda result: result['edits'][0].update(item_ids=['unapproved']),
        'duplicate': lambda result: result['edits'].append(deepcopy(result['edits'][0])),
        'unapproved-insert': lambda result: result['edits'][0].update(operation='insert', block_id='new', before='', item_ids=['t3']),
        'all-cut': lambda result: result['edits'][0].update(operation='delete', after=''),
        'speaker': lambda result: result['edits'][0].update(speaker='Someone else'),
    }
    provider.corrupt = corruptions[corruption]
    job = run_stage(client, run_id, 'scene-patch')[0]
    assert job['status'] == 'error' and job['output'] and job['result'] is None
    assert not get_plan(client, run_id)['patch']['complete']


def test_patch_invalidation_and_explicit_single_correction(client, story):
    run_id, provider = ready_patch(client, story)
    selected_stage(client, run_id, 'scene-patch')
    provider.fail_check = True
    check = selected_stage(client, run_id, 'scene-patch-check')
    assert not get_plan(client, run_id)['patch']['checked']
    assert preview(client, run_id, 'scene-patch').status_code == 409
    decide(client, run_id, 'repair-patch')
    second = selected_stage(client, run_id, 'scene-patch')
    assert decode(second['snapshot']['content'])['repair_context']['scene-patch-check'] == check['result']
    selected_stage(client, run_id, 'scene-patch-check')
    run = get_plan(client, run_id)
    response = client.post(f'/api/scenes/{run_id}/repair-patch', json={'operation_id': uuid4().hex, 'expected_revision': run['revision']})
    assert response.status_code == 409 and 'already used' in response.text
    reselect = client.post(f'/api/scenes/{run_id}/choose', json={'operation_id': uuid4().hex,
                           'expected_revision': run['revision'], 'job_id': second['id']})
    assert reselect.status_code == 409 and 'cannot reset' in reselect.text
    archive, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, archive)
    restored = get_plan(client, mapping[run_id])
    assert restored['state']['repair_selections']['scene-patch-check'] == mapping[check['id']]
    assert [job['snapshot']['content'] for job in restored['jobs']] == [job['snapshot']['content'] for job in run['jobs']]
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    choose(client, run_id, next(job for job in run['jobs'] if job['step'] == 'scene-verify'))
    cleared = get_plan(client, run_id)
    assert cleared['state']['gate_b'] is None and cleared['patch'] is None
    assert not cleared['state']['repair_selections'] and cleared['state']['patch_round'] == 0


def test_patch_archive_rejects_changed_input_output_and_repair_links(client, story):
    run_id, _ = ready_patch(client, story)
    selected_stage(client, run_id, 'scene-patch')
    selected_stage(client, run_id, 'scene-patch-check')
    _, original = backup(client, story)
    for field in ('content', 'output', 'repair'):
        document = deepcopy(original)
        corrupt_patch_archive(document, field)
        response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
        assert response.status_code == 400, response.text


def test_patches_require_current_approval_and_empty_packages_skip_calls(client, story):
    run_id, _, _ = triage_ready(client, story)
    assert preview(client, run_id, 'scene-patch').status_code == 409
    rejected_claim(client, run_id)
    decide(client, run_id, 'approve-revision', {'package': 'B'})
    client.app.state.scene_runner.provider = PatchProvider()
    proposal = run_stage(client, run_id, 'scene-patch')[0]
    run = get_plan(client, run_id)
    evidence = run['revision_plan']['verifications']['t1']['evidence']
    resolution = {'disposition': 'overrule', 'reason': 'Primary evidence does not support this fixture finding.', 'action': '', 'evidence': evidence}
    decide(client, run_id, 'resolve', {'item_id': 't3', 'resolution': resolution})
    response = client.post(f'/api/scenes/{run_id}/choose', json={'operation_id': uuid4().hex,
                           'expected_revision': get_plan(client, run_id)['revision'], 'job_id': proposal['id']})
    assert response.status_code == 409
    decide(client, run_id, 'approve-revision', {'package': 'B'})
    run = get_plan(client, run_id)
    assert run['patch']['no_changes_required'] and run['patch']['checked']
    assert run['patch']['text'] == run['draft']['text']
    assert preview(client, run_id, 'scene-patch').status_code == 409
    backup(client, story)


def corrupt_patch_archive(document, field):
    job = next(job for job in document['data']['scene_jobs'] if job['step'] == 'scene-patch')
    if field == 'content':
        snapshot = decode(job['snapshot'])
        content = decode(snapshot['content'])
        content['package']['items'][0]['action'] = 'Unapproved replacement action.'
        snapshot['content'] = encode(content)
        job['snapshot'] = encode(snapshot)
    elif field == 'output':
        job['output'] = job['output'].replace('invitation open', 'door closed')
    else:
        row = document['data']['scene_runs'][0]
        state = decode(row['state'])
        state['repair_selections'] = {'scene-patch': job['id']}
        row['state'] = encode(state)


def test_structural_operations_preserve_untouched_blocks_and_check_only_neighbors():
    blocks = [{'id': f'p{index}', 'kind': 'prose', 'text': f'Paragraph {index}.'} for index in range(6)]
    context = {'stage': 'scene-patch', 'blocks': blocks, 'dialogue_split': False,
               'package': {'items': [{'id': 'hold', 'disposition': 'hold'}]}}
    edits = [edit('p2', 'replace', 'Paragraph 2.', 'A changed paragraph.'),
             edit('new', 'insert', '', 'An approved new beat.', 'p2'),
             edit('p4', 'delete', 'Paragraph 4.', ''), edit('p0', 'move', 'Paragraph 0.', 'Paragraph 0.', 'p5')]
    result = {'edits': edits, 'resolutions': [{'item_id': 'hold', 'status': 'addressed'}]}
    validate_patch(result, context)
    updated, changes = apply_edits(blocks, edits, 'scene-patch')
    assert [block['id'] for block in updated] == ['p1', 'p2', 'new', 'p3', 'p5', 'p0']
    assert updated[0] == blocks[1] and updated[3] == blocks[3]
    passages = passage_changes(changes, updated)
    assert [block['id'] for block in passages[0]['neighbors']] == ['p1', 'new']
    assert [block['id'] for block in passages[-1]['before_neighbors']] == ['p1']
    check_context = {'changes': passages, 'package': context['package']}
    checks = {'checks': [{'change_id': change['id'], 'quotes': [change['after'] or change['before']]} for change in passages],
              'resolutions': [{'item_id': 'hold'}], 'issues': []}
    validate_patch_check(checks, check_context)
    checks['checks'][0]['quotes'] = ['Paragraph 5.']
    with pytest.raises(DomainError, match='outside'):
        validate_patch_check(checks, check_context)


def edit(block_id, operation, before, after, anchor=None):
    return {'block_id': block_id, 'operation': operation, 'before': before, 'after': after,
            'anchor_id': anchor, 'speaker': '', 'item_ids': ['hold'], 'reason': 'Approved structural fixture.'}
