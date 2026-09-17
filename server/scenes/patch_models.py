from typing import Annotated, Literal

from pydantic import Field

from server.models import Input

Text = Annotated[str, Field(min_length=1, max_length=4000)]


class PatchEdit(Input):
    block_id: str = Field(min_length=1, max_length=100)
    operation: Literal['replace', 'delete', 'insert', 'move']
    before: str = Field(max_length=100000)
    after: str = Field(max_length=100000)
    anchor_id: str | None = None
    speaker: str = Field(default='', max_length=200)
    item_ids: list[Text] = Field(min_length=1, max_length=100)
    reason: Text


class PatchResolution(Input):
    item_id: Text
    status: Literal['addressed', 'no-change', 'defer-dialogue', 'blocked']
    reason: Text


class PatchOutput(Input):
    summary: Text
    edits: list[PatchEdit] = Field(default_factory=list, max_length=200)
    resolutions: list[PatchResolution] = Field(max_length=100)


class PassageCheck(Input):
    change_id: Text
    status: Literal['pass', 'revise']
    quotes: list[Text] = Field(min_length=1, max_length=5)
    reason: Text


class CheckedResolution(Input):
    item_id: Text
    status: Literal['addressed', 'unresolved']
    reason: Text


class PatchIssue(Input):
    change_id: Text
    quote: Text
    category: Text
    explanation: Text


class PatchCheckOutput(Input):
    summary: Text
    checks: list[PassageCheck] = Field(max_length=400)
    resolutions: list[CheckedResolution] = Field(max_length=100)
    issues: list[PatchIssue] = Field(default_factory=list, max_length=40)
