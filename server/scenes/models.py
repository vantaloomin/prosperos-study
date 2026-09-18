from typing import Literal

from pydantic import Field, model_validator

from server.models import Input
from server.scenes.chance_models import ChanceBoundary


class SceneCreate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    title: str = Field(min_length=1, max_length=120)
    direction: str = Field(min_length=1, max_length=30000)
    propose_options: bool = True
    dialogue_split: bool = False


class DialogueActor(Input):
    character_id: str | None = Field(default=None, min_length=1, max_length=100)
    subject: str | None = Field(default=None, min_length=1, max_length=160)
    slot_ids: list[str] = Field(min_length=1, max_length=200)
    briefing: str = Field(min_length=1, max_length=12000)

    @model_validator(mode='after')
    def identity(self):
        if bool(self.character_id) == bool(self.subject):
            raise ValueError('Choose exactly one Character identity or name-only viewpoint.')
        return self


class SceneStep(Input):
    expected_revision: int
    key: Literal["scene-options", "scene-beats", "scene-brief", "scene-draft", "scene-dialogue", "scene-coverage",
                 "scene-triage", "scene-verify", "scene-patch", "scene-dialogue-patch", "scene-patch-check", "scene-continuity"]
    dialogue_actors: list[DialogueActor] = Field(default_factory=list, min_length=1, max_length=8, exclude_if=lambda value: not value)
    profile_ids: list[str] = Field(default_factory=list, max_length=4)
    review_job_ids: list[str] = Field(default_factory=list, max_length=10)
    item_id: str | None = None


class SceneStart(SceneStep):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


class SceneChoice(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    job_id: str
    option_id: str | None = None


class Option(Input):
    id: Literal["A", "B", "C", "D"]
    title: str = Field(min_length=1, max_length=200)
    direction: str = Field(min_length=1, max_length=5000)
    opens: str = Field(min_length=1, max_length=2000)
    closes: str = Field(min_length=1, max_length=2000)


class OptionsOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    options: list[Option] = Field(min_length=4, max_length=4)


class Beat(Input):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    development: str = Field(min_length=1, max_length=5000)
    decision: str = Field(min_length=1, max_length=3000)
    constraints: str = Field(min_length=1, max_length=3000)
    chance: ChanceBoundary | None = Field(default=None, exclude_if=lambda value: value is None)


class BeatsOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    beats: list[Beat] = Field(min_length=1, max_length=24)
    ending: str = Field(min_length=1, max_length=4000)


class BriefFact(Input):
    source_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=4000)
    relevance: str = Field(min_length=1, max_length=4000)


class BriefOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    facts: list[BriefFact] = Field(default_factory=list, max_length=40)
    unknowns: list[str] = Field(default_factory=list, max_length=20)


class SceneEdit(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    plan: BeatsOutput


class SceneApproval(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    note: str = Field(default="", max_length=5000)


class SceneState(Input):
    selections: dict[str, str] = Field(default_factory=dict)
    option_id: str | None = None
    beat_edit: BeatsOutput | None = None
    gate_a: dict | None = None
    triage_edits: dict = Field(default_factory=dict)
    verifications: dict[str, str] = Field(default_factory=dict)
    gate_b: dict | None = None
    patch_round: Literal[0, 1] = 0
    repair_selections: dict[str, str] = Field(default_factory=dict)
    accepted: dict | None = None
