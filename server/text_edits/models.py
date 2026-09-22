from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExactInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)

    @field_validator('*')
    @classmethod
    def unicode_text(cls, value):
        if isinstance(value, str):
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
                raise ValueError('Text must contain complete Unicode characters.') from None
        return value


class TextTarget(ExactInput):
    kind: Literal['passage', 'story-brief', 'document', 'library-field', 'writing-field', 'prompt', 'candidate', 'scene-block']
    story_id: str = Field(min_length=1, max_length=100)
    branch_id: str | None = Field(default=None, min_length=1, max_length=100)
    node_id: str | None = Field(default=None, min_length=1, max_length=100)
    purpose: Literal['composer', 'author-note', 'scene-goal'] | None = None
    asset_id: str | None = Field(default=None, min_length=1, max_length=100)
    field: str | None = Field(default=None, min_length=1, max_length=100)
    item_id: str | None = Field(default=None, min_length=1, max_length=100)
    prompt_key: str | None = Field(default=None, min_length=1, max_length=100)
    prompt_scope: Literal['story', 'workspace'] | None = None
    workspace_id: str | None = Field(default=None, pattern=r'^(?:restored:)?[0-9a-f]{32}$')
    candidate_id: str | None = Field(default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None)
    scene_id: str | None = Field(default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None)
    job_id: str | None = Field(default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def shape(self):
        actual = self.model_fields_set - {'kind', 'story_id'}
        actual = {key for key in actual if getattr(self, key) is not None}
        expected = {'passage': {'branch_id', 'node_id'}, 'story-brief': set(), 'document': {'branch_id', 'purpose'},
                    'library-field': {'asset_id', 'field'}, 'writing-field': {'asset_id', 'field'},
                    'prompt': {'prompt_key', 'prompt_scope'}, 'candidate': {'branch_id', 'candidate_id'},
                    'scene-block': {'branch_id', 'scene_id', 'job_id', 'item_id'}}[self.kind].copy()
        if self.kind in {'library-field', 'writing-field'} and self.field in {'greeting', 'entry', 'step-instructions'}:
            expected.add('item_id')
        if self.kind == 'prompt' and self.prompt_scope == 'workspace':
            expected.add('workspace_id')
        if actual != expected:
            raise ValueError('Supply only the identities required for this text target.')
        return self


class TargetRead(ExactInput):
    target: TextTarget


class TargetCatalog(ExactInput):
    story_id: str = Field(min_length=1, max_length=100)
    kind: Literal['library-field', 'writing-field', 'prompt']
    asset_id: str | None = Field(default=None, min_length=1, max_length=100)
    prompt_key: str | None = Field(default=None, min_length=1, max_length=100)
    prompt_scope: Literal['story', 'workspace'] | None = None


class TextSelection(ExactInput):
    start: int = Field(ge=0, le=200000)
    end: int = Field(ge=0, le=200000)
    text: str = Field(max_length=100000)


class Command(ExactInput):
    operation_id: str = Field(min_length=8, max_length=100)


class DocumentWrite(TargetRead):
    expected_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    text: str = Field(max_length=100000)


class DocumentSave(Command, TargetRead):
    # Keep the existing field order used by saved operation fingerprints.
    expected_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    text: str = Field(max_length=100000)


class ProposalCreate(Command, TargetRead):
    expected_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    selection: TextSelection
    action: Literal['add', 'insert-before', 'insert-after', 'replace', 'update']
    replacement: str = Field(max_length=100000)
    explanation: str = Field(default='', max_length=2000)


class ProposalChange(Command):
    expected_revision: int = Field(ge=0)
    replacement: str = Field(max_length=100000)
    explanation: str = Field(default='', max_length=2000)


class ProposalDecision(Command):
    expected_revision: int = Field(ge=0)
    branch_name: str = Field(default='Revised telling', min_length=1, max_length=120)
    acknowledge_state_reset: bool = False


class UndoCommand(Command):
    acknowledge_state_reset: bool = False


class ProposalRebase(ProposalCreate):
    expected_revision: int = Field(ge=0)
