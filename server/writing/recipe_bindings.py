"""Live identities sit beside frozen compiler inputs, including after repeated restore."""
from copy import deepcopy

IDENTITIES = {'id', 'story_id', 'branch_id', 'head_id', 'manifest_id', 'forked_from', 'fork_node_id', 'node_id',
              'asset_id', 'version_id', 'document_id', 'generation_id', 'candidate_id', 'scene_id', 'job_id',
              'draft_id', 'receipt_id', 'edit_receipt_id', 'cleanup_id'}


def initial_bindings(snapshot):
    values = set(snapshot['writing_versions'])
    for record in (snapshot['branch'], snapshot['sources']['boundary'], snapshot['target']['ref'], snapshot['target']['basis']):
        values.update(value for key, value in record.items() if key in IDENTITIES and isinstance(value, str))
    for stage in snapshot['plan']:
        for template in stage['templates']:
            values.update([template['profile']['id'], template['profile']['profile_id'], template['prompt']['id']])
            values.update(section['id'] for section in template['prompt_sections'])
    values.update(table['id'] for table in snapshot['chance']['tables'].values())
    return {value: value for value in sorted(values)}


def bind_job(job, bindings):
    result = deepcopy(job)
    for key in ('profile', 'prompt'):
        result[key]['id'] = bindings[result[key]['id']]
    result['profile']['profile_id'] = bindings[result['profile']['profile_id']]
    for section in result['prompt_sections']:
        section['id'] = bindings[section['id']]
    return result


def public_value(value):
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, dict):
        return {key: public_value(item) for key, item in value.items() if key != 'credential_ref'}
    return value


def redact_plan(snapshot):
    result = deepcopy(snapshot)
    for stage in result['plan']:
        for template in stage['templates']:
            template['profile']['credential_ref'] = None
    return result
