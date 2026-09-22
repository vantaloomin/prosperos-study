from typing import Literal

from pydantic import Field, StrictBool, model_validator

from server.mechanics.models import Beat, RngSettings
from server.text_edits.models import ExactInput, TextSelection, TextTarget
from server.writing.models import WritingChoices


class RecipeRunPreview(ExactInput):
    expected_revision: int = Field(ge=0)
    target: TextTarget
    expected_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    selection: TextSelection
    action: Literal['replace', 'insert-before', 'insert-after', 'add', 'update'] = 'replace'
    direction: str = Field(default='', max_length=30000)
    writing: WritingChoices = Field(default_factory=WritingChoices)
    profiles: dict[Literal['writer', 'review', 'revision'], str] = Field(default_factory=dict, max_length=3)
    task_switches: dict[str, StrictBool] = Field(default_factory=dict, max_length=100)
    review_lenses: list[str] | None = Field(default=None, min_length=1, max_length=11)
    randomness: RngSettings | None = None
    beat: Beat | None = None

    @model_validator(mode='after')
    def nonblank_profiles(self):
        if any(not value.strip() or len(value) > 100 for value in self.profiles.values()):
            raise ValueError('Choose a valid model assignment for each recipe task.')
        return self


class RecipeRunCreate(RecipeRunPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class RecipeStepStart(ExactInput):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    preview_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class RecipeJobCommand(ExactInput):
    expected_attempt: int = Field(ge=0)
