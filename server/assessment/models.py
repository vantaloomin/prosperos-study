from pydantic import Field

from server.mechanics.models import Beat
from server.models import Input


class Evidence(Input):
    node_id: str
    quote: str = Field(min_length=1, max_length=4000)


class AssessedBeat(Beat):
    completed: bool
    waiting_for_player: bool
    protected: bool
    resolves_event: bool
    new_scene: bool


class AssessmentOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    boundary_node_id: str | None = None
    beat: AssessedBeat
    evidence: list[Evidence] = Field(default_factory=list, max_length=8)


class AssessmentDecision(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    job_id: str | None = None
    without_chance: bool = False
