from typing import Literal

from pydantic import Field, model_validator

from server.models import Input


class RoutingUpdate(Input):
    expected_revision: int
    primary_profile_id: str | None = None
    step_profiles: dict[str, str] = Field(default_factory=dict)


class ReviewStep(Input):
    key: str
    profile_ids: list[str] = Field(default_factory=list, max_length=4)


class ReviewPreview(Input):
    expected_revision: int
    from_node_id: str | None = None
    through_node_id: str | None = None
    scene_id: str | None = None
    scene_revision: int | None = Field(default=None, ge=0)
    steps: list[ReviewStep] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def distinct_target(self):
        if (self.scene_id is None) != (self.scene_revision is None):
            raise ValueError("A scene review needs both the saved plan and its revision.")
        if self.scene_id is not None and (self.from_node_id or self.through_node_id):
            raise ValueError("Choose a saved draft or a Story passage, not both.")
        return self


class ReviewStart(ReviewPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


class SelectReview(Input):
    job_id: str


class Finding(Input):
    severity: Literal["hard", "soft", "cut", "hold"]
    source_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=4000)
    suggestion: str = Field(min_length=1, max_length=4000)


class ReviewOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    findings: list[Finding] = Field(max_length=10)
