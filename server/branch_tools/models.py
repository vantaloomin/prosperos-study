from pydantic import Field

from server.models import Input


class CurationUpdate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    favorite: bool
    archived: bool


class ComparisonCreate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    left_branch_id: str
    right_branch_id: str
    left_revision: int = Field(ge=0)
    right_revision: int = Field(ge=0)


class BranchSearch(Input):
    query: str = Field(min_length=1, max_length=200)
    branch_ids: list[str] = Field(default_factory=list, max_length=1000)
    include_archived: bool = False
    include_removed: bool = False
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30, ge=1, le=100)
