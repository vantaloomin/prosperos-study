from pydantic import Field

from server.models import Input


class ContextPreviewRequest(Input):
    expected_revision: int
    profile_ids: list[str] = Field(default_factory=list, max_length=4)
    direction: str = Field(default="", max_length=30000)
    knowledge_subject: str | None = Field(default=None, min_length=1, max_length=160)
    knowledge_character_id: str | None = Field(default=None, min_length=1, max_length=100)
    use_prepared_beat: bool = True
    assess_beat: bool = True
    assessment_profile_ids: list[str] = Field(default_factory=list, max_length=4)


class GenerateRequest(ContextPreviewRequest):
    operation_id: str = Field(min_length=8, max_length=100)
    reviewed_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class AcceptCandidate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    as_new_branch: bool = False
    branch_name: str = Field(default="Another telling", min_length=1, max_length=120)


class AlternateRequest(Input):
    operation_id: str = Field(min_length=8, max_length=100)


class RetryCandidate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_attempt: int = Field(ge=0)


def semantic_request(body):
    return body.model_dump(exclude={'operation_id', 'reviewed_fingerprint'}, exclude_none=True)
