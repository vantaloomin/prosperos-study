import json

from pydantic import ValidationError

from server.authoring.models import AuthoringOutput
from server.database import decode, encode, one
from server.errors import DomainError, require
from server.workflow.context import job_snapshot, snapshot_hash
from server.workflow.models import ReviewStep


def defaults(connection):
    row = connection.execute("SELECT value FROM preferences WHERE key='authoring_profiles'").fetchone()
    return decode(row['value']) if row else {}


def authoring_snapshot(connection, body):
    asset_id = None
    if body.source_version_id:
        source = one(connection, 'SELECT v.asset_id,a.kind FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE v.id=?', (body.source_version_id,))
        require(('character' if source['kind'] == 'persona' else source['kind']) == ('character' if body.kind == 'persona' else body.kind), 'The source version belongs to another kind of Library item.')
        asset_id = source['asset_id']
    context = {'kind': body.kind, 'name': body.name, 'direction': body.direction,
        'target': {'key': body.target_key, 'label': body.target_label, 'text': body.text},
        'supporting_fields': body.context, 'sources': []}
    selection = ReviewStep(key=body.step, profile_ids=body.profile_ids)
    jobs = job_snapshot(connection, {'settings': encode({'step_profiles': defaults(connection)})}, selection, context)
    return {'asset_id': asset_id, 'source_version_id': body.source_version_id, 'draft_id': body.draft_id,
            'kind': body.kind, 'name': body.name, 'target_key': body.target_key, 'step': body.step, 'content': jobs[0]['content'], 'jobs': jobs}


def preview_view(snapshot):
    return {'preview_hash': snapshot_hash(snapshot), 'request_count': len(snapshot['jobs']), 'jobs': [
        {'profile_name': job['profile']['name'], 'model': job['profile']['config']['model'],
         'provider': job['profile']['config']['provider'], 'prompt_version': job['prompt']['number'],
         'estimated_input_tokens': job['estimated_input_tokens'], 'content': job['content'],
         'prompt': job['prompt']['template']} for job in snapshot['jobs']]}


def parse_authoring(output, snapshot):
    try:
        result = AuthoringOutput.model_validate(json.loads(output))
    except (ValueError, ValidationError) as error:
        raise DomainError('The assistant returned an invalid proposal. Its text is preserved; inspect the prompt or retry.', 502) from error
    original = decode(snapshot['content'])['target']['text']
    require(all(finding.quote in original for finding in result.findings), 'A finding quotes text outside the reviewed field.', 502)
    if snapshot['step'] == 'authoring-critique':
        require(result.proposal is None, 'Critique must return observations, not a replacement.', 502)
    else:
        require(result.proposal is not None and bool(result.proposal.strip()), 'Drafting and tightening require a nonempty proposal.', 502)
    return result.model_dump()
