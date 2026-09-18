from typing import Literal

from pydantic import Field, model_validator

from server.memory.planned_events import PlannedEvent, validate_plan_update
from server.memory.source_evidence import quotation_matches
from server.models import Input
from server.scenes.models import SceneApproval


class ContinuityEvidence(Input):
    source_id: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=5000)


class ContinuityChange(Input):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    action: Literal['add', 'replace', 'resolve']
    target_id: str | None = Field(default=None, max_length=200)
    kind: Literal['fact', 'knowledge', 'thread', 'plan']
    subject: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=5000)
    reason: str = Field(min_length=1, max_length=3000)
    evidence: list[ContinuityEvidence] = Field(min_length=1, max_length=8)
    plan: PlannedEvent | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def plan_matches_kind(self):
        if (self.kind == 'plan') != (self.plan is not None):
            raise ValueError('Only a plan entry must carry a structured plan.')
        return self


class ContinuityOutput(Input):
    summary: str = Field(min_length=1, max_length=5000)
    scene_summary: str = Field(min_length=1, max_length=5000)
    summary_quote: str = Field(min_length=1, max_length=5000)
    changes: list[ContinuityChange] = Field(default_factory=list, max_length=100)


class SceneAcceptance(SceneApproval):
    manual_review: bool = False
    selected_ids: list[str] = Field(default_factory=list, max_length=100)
    include_summary: bool = False
    as_new_branch: bool = False
    branch_name: str = Field(default='Accepted scene', min_length=1, max_length=120)


def validate_continuity(result, context):
    from server.errors import require

    sources = {item['id']: item for item in context['sources']}
    require(quotation_matches(sources['scene:checked'], result['summary_quote']), 'The summary needs an exact checked-scene quotation.', 502)
    changes = result['changes']
    require(len({item['id'] for item in changes}) == len(changes), 'Continuity change IDs must be unique.', 502)
    targets = [item['target_id'] for item in changes if item['target_id']]
    require(len(targets) == len(set(targets)), 'Propose at most one update per continuity entry.', 502)
    existing = {item['id']: item for item in context['existing_entries']}
    for change in changes:
        validate_change(change, sources, existing)


def validate_change(change, sources, existing, *, required_source='scene:checked'):
    from server.errors import require

    validate_citations(change['evidence'], sources, required_source)
    if change['action'] == 'add':
        require(change['target_id'] is None, 'A new continuity entry cannot replace an existing target.', 502)
        validate_plan_update(change)
        return
    target = existing.get(change['target_id'])
    require(target is not None, 'A continuity update targets a fact outside this path.', 502)
    require(target['kind'] == change['kind'] and target['subject'] == change['subject'],
            'An update must preserve the entry kind and subject.', 502)
    validate_plan_update(change, target)
    require(change['action'] != 'resolve' or change['kind'] == 'thread', 'Only a thread may be resolved.', 502)

def validate_citations(evidence, sources, required_source):
    from server.errors import require
    if required_source:
        require(any(item['source_id'] == required_source for item in evidence),
                'Every continuity change needs evidence from the checked scene.', 502)
    for citation in evidence:
        require(citation['source_id'] in sources and quotation_matches(sources[citation['source_id']], citation['quote']),
                'A continuity quotation is missing or outside its supplied source.', 502)
