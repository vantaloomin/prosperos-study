"""Read-only prospective writing inputs; no provider dispatch or random draws."""
from typing import Literal

from pydantic import Field

from server.assessment.context import assessment_input, assessment_needed
from server.assessment.writing import saved_boundary
from server.context_report import (
    input_sections,
    preview_fingerprint,
    profile_budget,
    section_page,
    section_summaries,
)
from server.database import one
from server.errors import require
from server.generation_context import generation_snapshot
from server.generation_models import ContextPreviewRequest
from server.mechanics.config import read_settings
from server.mechanics.state import node_state
from server.workflow.context import job_snapshot
from server.workflow.models import ReviewStep


class ContextSectionRequest(ContextPreviewRequest):
    fingerprint: str = Field(min_length=64, max_length=64)
    section: str = Field(min_length=1, max_length=100)
    offset: int = Field(default=0, ge=0)
    view: Literal['readable', 'exact'] = 'readable'


def assessment_preview(connection, snapshot, body):
    branch = snapshot['branch']
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    if not assessment_needed(story, snapshot, body) or saved_boundary(connection, branch):
        return {'status': 'none', 'budgets': []}
    existing = connection.execute('SELECT id,generation_id FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                  (branch['id'], branch['head_id'] or '')).fetchone()
    if existing:
        return {'status': 'completed' if existing['generation_id'] else 'saved',
                'assessment_id': existing['id'], 'budgets': []}
    context = assessment_input(snapshot, node_state(connection, branch['head_id']), read_settings(story))
    selection = ReviewStep(key='beat-assessment', profile_ids=body.assessment_profile_ids)
    jobs = job_snapshot(connection, story, selection, context, validate_budget=False)
    return {'status': 'new', 'budgets': [profile_budget(job['profile'], job['estimated_input_tokens']) for job in jobs]}


def inspect_context(connection, branch_id, body):
    snapshot, profiles = generation_snapshot(connection, branch_id, body, validate_budget=False)
    sections = input_sections(snapshot)
    budgets = [profile_budget(profile, snapshot['estimated_input_tokens']) for profile in profiles]
    assessment = assessment_preview(connection, snapshot, body)
    fingerprint = preview_fingerprint(snapshot, budgets, assessment)
    report = {'fingerprint': fingerprint, 'branch_id': branch_id, 'head_id': snapshot['branch']['head_id'],
              'branch_revision': snapshot['branch']['revision'], 'story_revision': snapshot['story_revision'],
              'prompt_version': snapshot['prompt']['number'], 'coverage': snapshot['coverage'],
              'budgets': budgets, 'assessment': assessment, 'sections': section_summaries(sections)}
    return report, snapshot, sections


class ContextInspector:
    def __init__(self, database):
        self.database = database

    def preview(self, branch_id, body):
        with self.database.connect() as connection:
            return inspect_context(connection, branch_id, body)[0]

    def section(self, branch_id, body):
        with self.database.connect() as connection:
            report, snapshot, sections = inspect_context(connection, branch_id, body)
            require(report['fingerprint'] == body.fingerprint,
                    'These inputs changed after the preview. Refresh the context preview before reading more.', 409)
            return section_page(snapshot, sections, body.section, body.offset, body.view)
