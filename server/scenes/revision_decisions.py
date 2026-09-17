from server.database import decode, now, one
from server.errors import require
from server.scenes.revision_context import triage_context, triage_item
from server.scenes.revision_models import validate_triage
from server.scenes.state import clear_patches, selected_result


def resolved_triage(connection, run):
    original = selected_result(connection, run, 'scene-triage')
    if not original:
        return None
    edits = run['state'].get('triage_edits', {})
    return {**original, 'items': [{**item, **edits.get(item['id'], {})} for item in original['items']]}


def resolve_item(connection, run, body):
    original = triage_item(connection, run, body.item_id)
    if original['disposition'] == 'verify' and body.resolution.disposition != 'verify':
        require(body.item_id in run['state'].get('verifications', {}), 'Choose a verification verdict before resolving this disputed item.', 409)
    state = run['state']
    state['triage_edits'][body.item_id] = body.resolution.model_dump()
    validate_triage(resolved_triage(connection, run), triage_context(connection, run))
    state['gate_b'] = None
    clear_patches(state)
    return state


def package_items(result, context, package, requested):
    findings = {finding['id']: finding for finding in context['findings']}
    items = result['items']
    if package == 'custom':
        require(len(requested) == len(set(requested)), 'A package cannot repeat an item.')
        require(set(requested) <= {item['id'] for item in items}, 'A package refers to an unknown item.')
        chosen = [item for item in items if item['id'] in requested]
    else:
        require(not requested, 'Named packages calculate their items from the saved triage.')
        chosen = [item for item in items if included(item, findings, package)]
    required = {item['id'] for item in items if mandatory(item, findings)}
    require(required <= {item['id'] for item in chosen}, 'The package must address every hard fix.')
    require(all(item['disposition'] not in {'overrule', 'verify'} for item in chosen), 'Only resolved proposed changes can enter a package.')
    return chosen


def mandatory(item, findings):
    return item['disposition'] == 'hard-fix' or (item['disposition'] == 'hold' and
            any(findings[ref]['severity'] == 'hard' for ref in item['finding_ids']))


def included(item, findings, package):
    disposition = item['disposition']
    if disposition in {'overrule', 'verify'}:
        return False
    if disposition == 'hold':
        return package == 'C' or mandatory(item, findings)
    canon = any(findings[ref]['role'] == 'review-continuity' for ref in item['finding_ids'])
    return disposition == 'hard-fix' or canon or package in {'B', 'C'}


def approve_revision(connection, run, body):
    result = resolved_triage(connection, run)
    require(result and result['approach'] == 'patch', 'Choose a patchable triage result; a redraft recommendation returns to drafting.', 409)
    require(not run['state'].get('gate_b'), 'This revision package is already approved.', 409)
    require(all(item['disposition'] != 'verify' for item in result['items']), 'Resolve every disputed item before the second director gate.', 409)
    chosen = package_items(result, triage_context(connection, run), body.package, body.item_ids)
    holds = {item['id'] for item in chosen if item['disposition'] == 'hold'}
    require(holds == set(body.confirmed_hold_ids), 'Explicitly confirm every structural change included in this package.')
    state = run['state']
    state['gate_b'] = {'approved_at': now(), 'note': body.note, 'package': body.package,
                       'item_ids': [item['id'] for item in chosen], 'items': chosen,
                       'confirmed_hold_ids': sorted(holds), 'triage_job_id': state['selections']['scene-triage']}
    return state


def revision_view(connection, run):
    result = resolved_triage(connection, run)
    if not result:
        return None
    context = triage_context(connection, run)
    verifications = {}
    for item_id, job_id in run['state'].get('verifications', {}).items():
        row = one(connection, 'SELECT result FROM scene_jobs WHERE id=?', (job_id,))
        verifications[item_id] = {'job_id': job_id, **decode(row['result'])}
    return {**result, 'findings': context['findings'], 'sources': context['sources'], 'verifications': verifications,
            'packages': {key: [item['id'] for item in package_items(result, context, key, [])] for key in ('A', 'B', 'C')}}
