from server.database import decode, many, one
from server.errors import require
from server.lore.scene import planned_sources
from server.memory.source_evidence import carry_evidence, cited_ids
from server.scenes.chance import chance_sources
from server.scenes.drafts import assemble_draft, coverage_passes
from server.scenes.state import reviewed_state, selected_result


def revision_sources(connection, run, coverage=None):
    draft = assemble_draft(selected_result(connection, run, 'scene-draft'), selected_result(connection, run, 'scene-dialogue'))
    covered = coverage_passes(coverage or selected_result(connection, run, 'scene-coverage')) or 'scene-coverage' in run['snapshot'].get('disabled_steps', [])
    require(draft and draft['complete'] and covered,
            'Choose a complete draft and passing coverage before triage.', 409)
    chance = chance_sources(run) if run['snapshot'].get('workflow_version', 1) == 1 else []
    return planned_sources(run, [*run['snapshot']['sources'], *chance, {'id': 'revision:draft', 'kind': 'draft',
            'title': 'Proposed scene, not accepted history', 'text': draft['text']}])


def review_report(connection, run, job_id, alias):
    job = one(connection, 'SELECT * FROM review_jobs WHERE id=?', (job_id,))
    review = one(connection, 'SELECT snapshot FROM review_runs WHERE id=?', (job['run_id'],))
    target = decode(review['snapshot']).get('scene')
    require(target and target['id'] == run['id'] and reviewed_state(target['state']) == reviewed_state(run['state']),
            'Select independent reports of this exact scene draft and plan.', 409)
    require(job['status'] == 'done', 'Only completed reports can enter triage.', 409)
    result = decode(job['result'])
    findings = [{**item, 'id': f'{alias}f{index + 1}', 'role': job['step']} for index, item in enumerate(result['findings'])]
    return {'role': job['step'], 'summary': result['summary'], 'findings': findings}


def triage_inputs(connection, run, job_ids):
    require(job_ids and len(job_ids) == len(set(job_ids)), 'Choose completed reports for triage, without duplicates.')
    reports = [review_report(connection, run, job_id, f'r{index + 1}') for index, job_id in enumerate(job_ids)]
    require(len({report['role'] for report in reports}) == len(reports), 'Choose one comparison result per reviewer role.')
    coverage = None
    if run['snapshot'].get('workflow_version', 1) >= 2 and 'scene-coverage' not in run['snapshot'].get('disabled_steps', []):
        from server.scenes.reader_coverage import selected_coverage
        coverage = selected_coverage(connection, run, job_ids)
        require(coverage_passes(coverage),
                'Include a passing informed beat-coverage report for this draft; redraft missing or changed beats first.', 409)
    sources = revision_sources(connection, run, coverage)
    available = []
    for job_id in job_ids:
        job = one(connection, 'SELECT snapshot FROM review_jobs WHERE id=?', (job_id,))
        snapshot = decode(job['snapshot'])
        if snapshot.get('source_memory'):
            available.extend(decode(snapshot['content'])['sources'])
    sources = carry_evidence(sources, cited_ids(reports), available)
    return {'stage': 'scene-triage', 'sources': sources, 'reports': reports,
            **({'inline_verification': True} if run['snapshot'].get('workflow_version', 1) >= 2 else {}),
            'findings': [finding for report in reports for finding in report['findings']],
            'approved_beats': selected_result(connection, run, 'scene-beats')}


def triage_context(connection, run):
    job_id = run['state']['selections'].get('scene-triage')
    require(job_id, 'Choose a triage result first.', 409)
    job = one(connection, 'SELECT snapshot FROM scene_jobs WHERE id=?', (job_id,))
    return decode(decode(job['snapshot'])['content'])


def triage_item(connection, run, item_id):
    result = selected_result(connection, run, 'scene-triage')
    require(result, 'Choose a triage result first.', 409)
    item = next((item for item in result['items'] if item['id'] == item_id), None)
    require(item, 'Choose an item from the selected triage result.')
    return item


def verification_inputs(connection, run, item_id):
    item = triage_item(connection, run, item_id)
    context = triage_context(connection, run)
    return {'stage': 'scene-verify', 'sources': context['sources'], 'item': item,
            'findings': [finding for finding in context['findings'] if finding['id'] in item['finding_ids']]}


def revision_inputs(connection, run, body):
    if body.key == 'scene-triage':
        require(body.item_id is None, 'Triage covers all selected findings.')
        return triage_inputs(connection, run, body.review_job_ids)
    require(not body.review_job_ids and body.item_id, 'Verification targets one selected triage item.')
    return verification_inputs(connection, run, body.item_id)


def available_reports(connection, run):
    rows = many(connection, "SELECT j.*,r.snapshot AS target,r.selections AS preferred,r.created_at AS reviewed_at "
                "FROM review_jobs j JOIN review_runs r ON r.id=j.run_id WHERE r.branch_id=? "
                "AND json_extract(r.snapshot,'$.scene.id')=? ORDER BY r.created_at DESC,j.rowid", (run['branch_id'], run['id']))
    result = []
    for row in rows:
        target = decode(row['target'])['scene']
        if row['status'] != 'done' or reviewed_state(target['state']) != reviewed_state(run['state']):
            continue
        snapshot = decode(row['snapshot'])
        result.append({'id': row['id'], 'step': row['step'], 'profile_name': snapshot['profile']['name'],
                       'created_at': row['reviewed_at'], 'findings': len(decode(row['result'])['findings']),
                       'preferred': decode(row['preferred']).get(row['step']) == row['id']})
    return result
