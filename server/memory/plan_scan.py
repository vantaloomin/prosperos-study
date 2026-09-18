"""Bounded suggestions from accepted prose using the existing continuity role."""
from types import SimpleNamespace

from pydantic import Field, model_validator

from server.branches import path_nodes
from server.continuity import continuity_view
from server.database import decode, encode, one
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.plan_edits import plan_sources
from server.memory.plan_packet import compact_plan
from server.memory.plan_state import plan_head
from server.models import Input
from server.stories import check_revision
from server.workflow.context import job_snapshot, snapshot_hash, validate_job_budget

PURPOSE = 'planned-continuity-v1'
TASK = (
    'The checked scene is a bounded batch of already accepted prose, not a new scene. '
    'Propose only kind=plan changes established in that batch; changes may be empty. '
    'Quote only scene:checked, using a quotation contained within one supplied passage. '
    'Existing entries reflect the current branch. Do not reverse newer developments based on older prose. '
    'Omitted plans may make an indirect reference ambiguous: leave ambiguous changes unproposed. '
    'These are suggestions only; nothing is applied and no story text is written.'
)


class PlanScanPreview(Input):
    expected_revision: int = Field(ge=0)
    limit: int = Field(default=4, ge=1, le=8)
    from_beginning: bool = False
    latest_only: bool = False
    profile_ids: list[str] = Field(default_factory=list, max_length=4)


    @model_validator(mode='after')
    def one_range(self):
        if self.from_beginning and self.latest_only:
            raise ValueError('Choose the beginning or latest excerpt, not both.')
        return self


class PlanScanStart(PlanScanPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


def reviewed_sources(connection, branch_id):
    rows = connection.execute(
        "SELECT r.snapshot FROM review_runs r WHERE r.branch_id=? "
        "AND json_extract(r.snapshot,'$.purpose')=? AND EXISTS "
        "(SELECT 1 FROM review_jobs j WHERE j.run_id=r.id AND j.status='done')",
        (branch_id, PURPOSE)).fetchall()
    return {source_id for row in rows for source_id in decode(row['snapshot'])['scan_source_ids']}


def pending_sources(connection, branch, body):
    sources = list(plan_sources(connection, branch['head_id']))
    seen = reviewed_sources(connection, branch['id']) & {source['id'] for source in sources}
    pending = sources if body.from_beginning else [source for source in sources if source['id'] not in seen]
    selected = sources[-1:] if body.latest_only else pending[:body.limit]
    require(selected, 'No unreviewed accepted prose on this path. You can review from the beginning.', 409)
    covered = seen | {source['id'] for source in selected}
    return selected, sum(source['id'] not in covered for source in sources), sorted(seen)


def plan_context(sources, entries, omitted):
    passages = [{key: value for key, value in source.items() if key != 'node_id'} for source in sources]
    return {'task': TASK, 'passages': passages, 'existing_entries': entries, 'omitted_plans': omitted,
            'sources': [{'id': 'scene:checked', 'kind': 'accepted prose', 'title': 'Accepted passages',
                         'text': '\n\n'.join(source['text'] for source in passages)}]}


def eligible_plans(connection, branch, version):
    entries = continuity_view(connection, branch['head_id'], version)['entries']
    positions = {node['id']: index for index, node in enumerate(path_nodes(connection, branch['head_id']))}
    plans = sorted((item for item in entries if item['kind'] == 'plan'),
                   key=lambda item: (item['status'] == 'active', positions.get(item['node_id'], -1)), reverse=True)
    return [{**compact_plan(entry), 'kind': 'plan', 'status': entry['status']} for entry in plans]


def fit_plan_context(context, plans, jobs):
    capacity = min(job['profile']['config']['context_tokens'] - job['profile']['config']['max_output_tokens'] for job in jobs)
    prompt = jobs[0]['prompt']['template']
    selected = []
    for plan in plans:
        trial = {**context, 'existing_entries': [*selected, plan], 'omitted_plans': len(plans) - len(selected) - 1}
        if token_estimate(prompt, trial) <= capacity:
            selected.append(plan)
    return {**context, 'existing_entries': selected, 'omitted_plans': len(plans) - len(selected)}


def scan_snapshot(connection, branch_id, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    sources, remaining, seen = pending_sources(connection, branch, body)
    version = plan_head(connection, branch_id)
    plans = eligible_plans(connection, branch, version)
    context = plan_context(sources, [], len(plans))
    selection = SimpleNamespace(key='scene-continuity', profile_ids=body.profile_ids)
    jobs = job_snapshot(connection, story, selection, context, validate_budget=False)
    context = fit_plan_context(context, plans, jobs)
    estimate = token_estimate(jobs[0]['prompt']['template'], context)
    validate_job_budget([job['profile'] for job in jobs], estimate)
    jobs = [{**job, 'purpose': PURPOSE, 'content': encode(context), 'estimated_input_tokens': estimate} for job in jobs]
    return {'purpose': PURPOSE, 'branch': branch, 'story_revision': story['revision'],
            'continuity_version_id': version, 'scan_source_ids': [source['id'] for source in sources],
            'remaining_passages': remaining, 'reviewed_source_ids': seen, 'jobs': jobs}


def scan_preview(snapshot):
    context = decode(snapshot['jobs'][0]['content'])
    return {'preview_hash': snapshot_hash(snapshot), 'request_count': len(snapshot['jobs']),
            'passages': [{'id': source['id'], 'title': source['title'], 'text': source['text']} for source in context['passages']],
            'remaining_passages': snapshot['remaining_passages'], 'omitted_plans': context['omitted_plans'],
            'jobs': [{'profile_name': job['profile']['name'], 'model': job['profile']['config']['model'],
                      'prompt_version': job['prompt']['number'], 'estimated_input_tokens': job['estimated_input_tokens']}
                     for job in snapshot['jobs']]}
