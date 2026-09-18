"""One read-only contract shared by context inspection and guarded dispatch."""
import hashlib

from server.context_report import preview_fingerprint, profile_budget
from server.database import encode
from server.errors import require


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def assessment_contract(connection, snapshot, body):
    # Bookkeeping runs after acceptance. This preview describes only the exact
    # writer request, with any already prepared chance included in its content.
    return {'status': 'completed' if snapshot.get('opportunity_id') else 'none', 'budgets': []}


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
    require(contract['fingerprint'] == body.reviewed_fingerprint,
            'The inputs changed after your reviewed preview. Open Context budget and refresh the preview '
            'before generating. No model request was started.', 409)
    snapshot['reviewed_context'] = {'fingerprint': body.reviewed_fingerprint,
                                    'stage': 'writer'}
