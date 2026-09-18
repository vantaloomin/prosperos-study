from server.database import decode, one
from server.errors import require
from server.lore.scene import planned_sources
from server.memory.source_evidence import carry_evidence, cited_ids
from server.scenes.chance import chance_sources
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.drafts import assemble_draft
from server.scenes.patch_apply import apply_edits, compose, passage_changes
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.patch_validation import patch_check_passes
from server.scenes.revision_context import triage_context
from server.scenes.state import selected_result


def patch_keys(run):
    if run['snapshot'].get('workflow_version', 1) >= 2:
        return ['scene-patch']
    return [key for key in PATCH_KEYS if key != 'scene-dialogue-patch' or run['snapshot'].get('dialogue_split', False)]


def patch_writers(run):
    return [key for key in patch_keys(run) if key != 'scene-patch-check']


def patch_view(connection, run):
    gate = run['state'].get('gate_b')
    if not gate:
        return None
    draft = assemble_draft(selected_result(connection, run, 'scene-draft'), selected_result(connection, run, 'scene-dialogue'))
    blocks, changes, resolutions = draft['blocks'], [], []
    for key in patch_writers(run):
        result = selected_result(connection, run, key)
        if result:
            blocks, added = apply_edits(blocks, result['edits'], key)
            changes.extend(added)
            resolutions = result['resolutions']
    complete = not gate['items'] or all(key in run['state']['selections'] for key in patch_writers(run))
    blocked = any(item['status'] in {'blocked', 'defer-dialogue'} for item in resolutions)
    check = selected_result(connection, run, 'scene-patch-check')
    director = run['snapshot'].get('workflow_version', 1) >= 2
    return {'blocks': blocks, 'text': compose(blocks), 'changes': passage_changes(changes, blocks),
            'resolutions': resolutions, 'complete': complete, 'blocked': blocked, 'check': check,
            'checked': not gate['items'] or (complete and not blocked and (director or patch_check_passes(check))),
            **({'check_kind': 'director'} if director else {}),
            'no_changes_required': not gate['items']}


def original_blocks(connection, run):
    return assemble_draft(selected_result(connection, run, 'scene-draft'), selected_result(connection, run, 'scene-dialogue'))['blocks']


def patch_inputs(connection, run, key, version=1):
    require(version in {0, 1}, 'Unsupported patch context version.')
    gate = run['state'].get('gate_b')
    require(gate is not None, 'Approve the revision package before patching.', 409)
    require(bool(gate['items']), 'This package needs no changes or patch model calls.', 409)
    package = {name: gate[name] for name in ('package', 'items', 'item_ids', 'confirmed_hold_ids', 'note')}
    context = {'stage': key, 'package': package, 'sources': planned_sources(run, [*run['snapshot']['sources'], *chance_sources(run)]),
               'approved_beats': selected_result(connection, run, 'scene-beats'),
               'continuity_brief': selected_result(connection, run, 'scene-brief')}
    if run['snapshot'].get('workflow_version', 1) >= 2:
        context['unified_patch'] = True
    if version:
        ids = {ref for item in gate['items'] for ref in item['finding_ids']}
        context.update(context_version=version, approved_findings=[finding for finding in triage_context(connection, run)['findings'] if finding['id'] in ids])
    if run['snapshot'].get('memory_policy', {}).get('mode') == 'long':
        context['sources'] = carry_evidence(context['sources'], cited_ids(context), triage_context(connection, run)['sources'])
    if key == 'scene-patch-check':
        view = patch_view(connection, run)
        require(view['complete'] and not view['blocked'], 'Resolve every approved item before checking the patch.', 409)
        changes = view['changes'] if version else [{name: value for name, value in change.items() if name != 'before_neighbors'} for change in view['changes']]
        return {**context, 'changes': changes, 'writer_resolutions': view['resolutions']}
    require(not selected_result(connection, run, 'scene-patch-check'),
            'Use the explicit correction after a failed check, or revisit the package with the director.', 409)
    blocks = original_blocks(connection, run)
    prose = selected_result(connection, run, 'scene-patch') if key == 'scene-dialogue-patch' else None
    if prose:
        blocks, _ = apply_edits(blocks, prose['edits'], 'scene-patch')
    return {**context, 'blocks': blocks, 'dialogue_split': run['snapshot'].get('dialogue_split', False),
            'prior_edits': prose['edits'] if prose else [], 'prior_resolutions': prose['resolutions'] if prose else [],
            'repair_context': repair_context(connection, run)}


def repair_context(connection, run):
    result = {}
    for key, job_id in run['state'].get('repair_selections', {}).items():
        result[key] = decode(one(connection, 'SELECT result FROM scene_jobs WHERE id=?', (job_id,))['result'])
    return result


def repair_patch(connection, run, _body):
    check = selected_result(connection, run, 'scene-patch-check')
    require(check and not patch_check_passes(check), 'Choose a failed patch check before requesting its correction.', 409)
    state = run['state']
    require(state['patch_round'] == 0, 'The correction was already used. Revisit the revision package or redraft with the director.', 409)
    state['repair_selections'] = {key: value for key, value in state['selections'].items() if key in PATCH_KEYS}
    state['selections'] = {key: value for key, value in state['selections'].items() if key not in PATCH_KEYS + CONTINUITY_KEYS}
    state['patch_round'] = 1
    return state


def require_patch_choice(connection, run, key):
    if key not in {'scene-patch', 'scene-dialogue-patch'}:
        return
    check = selected_result(connection, run, 'scene-patch-check')
    require(not check or patch_check_passes(check),
            'A failed check requires the explicit correction or a newly approved package; reselecting a writer cannot reset it.', 409)
