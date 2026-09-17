from typing import Literal

from pydantic import Field

from server.models import Input


class InterpretationPreview(Input):
    expected_revision: int = Field(ge=0)
    key: Literal['background-interpretation'] = 'background-interpretation'
    profile_ids: list[str] = Field(default_factory=list, max_length=4)
    direction: str = Field(default='', max_length=12000)


class InterpretationStart(InterpretationPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


class InterpretationChoice(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    as_new_branch: bool = False
    branch_name: str = Field(default='Another private background', min_length=1, max_length=120)


class Basis(Input):
    source_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=4000)


class DriveInterpretation(Input):
    target_id: str = Field(min_length=1, max_length=50)
    motive: str = Field(min_length=1, max_length=3000)
    concealment: str = Field(min_length=1, max_length=3000)
    expression: str = Field(min_length=1, max_length=3000)
    basis: list[Basis] = Field(default_factory=list, max_length=6)


class HookInterpretation(Input):
    target_id: str = Field(min_length=1, max_length=50)
    event: str = Field(min_length=1, max_length=3000)
    foreshadowing: str = Field(min_length=1, max_length=3000)
    conditions: str = Field(min_length=1, max_length=3000)
    basis: list[Basis] = Field(default_factory=list, max_length=6)


class InterpretationOutput(Input):
    drives: list[DriveInterpretation] = Field(max_length=30)
    hooks: list[HookInterpretation] = Field(max_length=8)
