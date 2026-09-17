from pydantic import Field

from server.models import Input


class ContextPreviewRequest(Input):
    expected_revision: int
    profile_ids: list[str] = Field(default_factory=list, max_length=4)
    direction: str = Field(default="", max_length=30000)
    use_prepared_beat: bool = True
    assess_beat: bool = True
    assessment_profile_ids: list[str] = Field(default_factory=list, max_length=4)


class GenerateRequest(ContextPreviewRequest):
    operation_id: str = Field(min_length=8, max_length=100)


class AcceptCandidate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    as_new_branch: bool = False
    branch_name: str = Field(default="Another telling", min_length=1, max_length=120)


class AlternateRequest(Input):
    operation_id: str = Field(min_length=8, max_length=100)
