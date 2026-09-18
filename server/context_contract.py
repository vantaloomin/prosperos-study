"""One read-only contract shared by context inspection and guarded dispatch."""
import hashlib

from server.agent_switches import agent_enabled
from server.assessment.context import assessment_input, assessment_needed
from server.context_report import preview_fingerprint, profile_budget
from server.database import encode, one
from server.errors import require
from server.mechanics.config import configured_tables, read_settings
from server.mechanics.state import node_state
from server.workflow.context import job_snapshot
from server.workflow.models import ReviewStep


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def assessment_contract(connection, snapshot, body):
    branch = snapshot['branch']
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    boundary = connection.execute('SELECT id FROM mechanic_opportunities WHERE branch_id=? AND head_key=?',
                                  (branch['id'], branch['head_id'] or '')).fetchone()
    if (not agent_enabled(connection, 'beat-assessment', story)
            or not assessment_needed(story, snapshot, body) or boundary):
        return {'status': 'none', 'budgets': []}
    existing = connection.execute('SELECT * FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                  (branch['id'], branch['head_id'] or '')).fetchone()
    if existing:
        return {'status': 'completed' if existing['generation_id'] else 'saved',
                'assessment_id': existing['id'], 'budgets': [], 'input_fingerprint': digest(dict(existing))}
    settings = read_settings(story)
    tables = configured_tables(connection, settings)
    settings.table_versions = {key: value['id'] for key, value in tables.items()}
    before = node_state(connection, branch['head_id'])
    context = assessment_input(snapshot, before, settings)
    selection = ReviewStep(key='beat-assessment', profile_ids=body.assessment_profile_ids)
    jobs = job_snapshot(connection, story, selection, context, validate_budget=False)
    # Hash actual prompts, routing versions and table definitions, not just token counts.
    return {'status': 'new', 'budgets': [profile_budget(job['profile'], job['estimated_input_tokens']) for job in jobs],
            'input_fingerprint': digest({'settings': settings.model_dump(), 'tables': tables, 'jobs': jobs})}


def context_contract(connection, snapshot, profiles, body):
    overhead = snapshot.get('memory', snapshot.get('knowledge_lens', {})).get('overhead_margin', 0)
    budgets = [profile_budget(profile, snapshot['estimated_input_tokens'], overhead) for profile in profiles]
    assessment = assessment_contract(connection, snapshot, body)
    return {'fingerprint': preview_fingerprint(snapshot, budgets, assessment),
            'budgets': budgets, 'assessment': assessment}


def guard_reviewed_context(connection, snapshot, profiles, body):
    if body.reviewed_fingerprint is None:
        return
    contract = context_contract(connection, snapshot, profiles, body)
    require(contract['assessment']['status'] != 'saved',
            'A beat assessment is already saved here. Reopen it to continue from its frozen inputs.', 409)
    require(contract['fingerprint'] == body.reviewed_fingerprint,
            'The inputs changed after your reviewed preview. Open Context budget and refresh the preview '
            'before generating. No model request was started.', 409)
    snapshot['reviewed_context'] = {'fingerprint': body.reviewed_fingerprint,
                                    'stage': 'before_assessment' if contract['assessment']['status'] == 'new' else 'writer'}
