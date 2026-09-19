from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from server.models import Input


class PhraseChoice(Input):
    id: str = Field(pattern=r'^[0-9a-f]{64}$')
    phrase: str = Field(min_length=1, max_length=1000)


class CleanupChoices(Input):
    intentional: list[PhraseChoice] = Field(default_factory=list, max_length=200)
    dismissed: list[PhraseChoice] = Field(default_factory=list, max_length=200)


class CleanupSetting(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=0)
    enabled: bool
    timing: Literal['before_ready', 'reading'] = 'before_ready'


class CleanupSelection(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_attempt: int = Field(ge=1)
    original_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    selected: Literal['original', 'cleaned']


class Replacement(Input):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=200)]


class CleanupOutput(Input):
    replacements: list[Replacement] = Field(max_length=12)
