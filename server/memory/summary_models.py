from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from server.models import Input

Term = Annotated[str, Field(min_length=1, max_length=100)]
Quote = Annotated[str, Field(min_length=1, max_length=600)]


class SummaryItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_id: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1000)
    quotes: list[Quote] = Field(min_length=1, max_length=4)
    topics: list[Term] = Field(default_factory=list, max_length=8)
    aliases: list[Term] = Field(default_factory=list, max_length=8)


class SummaryOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    items: list[SummaryItem] = Field(max_length=8)


class SummaryPreview(Input):
    expected_revision: int = Field(ge=0)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    profile_ids: list[str] = Field(default_factory=list, max_length=4)


class SummaryStart(SummaryPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


class SummaryPublish(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    branch_id: str
    expected_revision: int = Field(ge=0)
    expected_version_id: str | None = None
    job_id: str
    result: SummaryOutput
    enabled: bool = True


class SummarySources(Input):
    offset: int = Field(default=0, ge=0)
