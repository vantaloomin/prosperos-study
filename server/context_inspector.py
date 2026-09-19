"""Read-only prospective writing inputs; no provider dispatch or random draws."""
from typing import Literal

from pydantic import Field

from server.context_contract import context_contract
from server.context_report import (
    input_sections,
    section_page,
    section_summaries,
)
from server.errors import require
from server.generation_context import generation_snapshot
from server.generation_models import ContextPreviewRequest
from server.memory.writer_recall import preview_recall


class ContextSectionRequest(ContextPreviewRequest):
    fingerprint: str = Field(min_length=64, max_length=64)
    section: str = Field(min_length=1, max_length=100)
    offset: int = Field(default=0, ge=0)
    view: Literal['readable', 'exact'] = 'readable'


def inspect_context(connection, branch_id, body):
    snapshot, profiles = generation_snapshot(connection, branch_id, body, validate_budget=False)
    sections = input_sections(snapshot)
    report = {**context_contract(connection, snapshot, profiles, body),
              'branch_id': branch_id, 'head_id': snapshot['branch']['head_id'],
              'branch_revision': snapshot['branch']['revision'], 'story_revision': snapshot['story_revision'],
              'prompt_version': snapshot['prompt']['number'], 'coverage': snapshot['coverage'],
              'sections': section_summaries(sections),
              **({'memory': snapshot['memory']} if 'memory' in snapshot else {}),
              **({'writer_recall': preview_recall(snapshot)} if 'writer_recall' in snapshot else {}),
              **({'knowledge_lens': snapshot['knowledge_lens']} if 'knowledge_lens' in snapshot else {})}
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
