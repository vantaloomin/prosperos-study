from typing import Literal

from pydantic import Field, model_validator

from server.models import Input

Key = str


class TableRow(Input):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    low: int = Field(ge=1, le=1000)
    high: int = Field(ge=1, le=1000)
    label: str = Field(min_length=1, max_length=200)
    instruction: str = Field(default="", max_length=6000)
    kind: Literal["event", "no_event", "progress"] = "event"
    child: str | None = None
    major: bool = False
    tags: list[str] = Field(default_factory=list, max_length=10)


class OverflowResult(Input):
    id: str
    label: str = Field(min_length=1, max_length=200)
    instruction: str = Field(max_length=6000)
    child: str | None = None
    domain_move: int = Field(ge=-1, le=1)


class TableDefinition(Input):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    name: str = Field(min_length=1, max_length=160)
    purpose: Literal["event", "handling", "carrier", "extra", "texture"] = "extra"
    die: int = Field(ge=1, le=1000)
    rows: list[TableRow] = Field(min_length=1, max_length=1000)
    note: str = Field(default="", max_length=3000)
    low_overflow: OverflowResult | None = None
    high_overflow: OverflowResult | None = None

    @model_validator(mode="after")
    def covered_ranges(self):
        if self.id == "handling" and self.die != 100:
            raise ValueError("The handling oracle uses d100; its modifiers and pressure cap depend on that scale.")
        cursor = 1
        ids = set()
        for row in sorted(self.rows, key=lambda item: item.low):
            if row.low != cursor or row.high < row.low or row.id in ids:
                raise ValueError("Every face must appear exactly once, with unique result IDs.")
            if row.kind != "event" and row.child:
                raise ValueError("No-event and progress results cannot have a child table.")
            cursor = row.high + 1
            ids.add(row.id)
        if cursor != self.die + 1:
            raise ValueError("The result ranges must cover the complete die.")
        return self


class TablePublish(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_version_id: str | None = None
    definition: TableDefinition


class RngSettings(Input):
    enabled: bool = False
    automatic_assessment: bool = Field(default=False, exclude_if=lambda value: not value)
    narrative_push: bool = True
    encounter: bool = True
    handling: bool = False
    proficiency: bool = True
    fracture: bool = True
    preparation: bool = True
    subresults: bool = True
    carriers: bool = True
    textures: bool = True
    pressure_cap: bool = True
    domain_progression: bool = True
    chance: int = Field(default=15, ge=0, le=100)
    cooldown: int = Field(default=3, ge=0, le=100)
    major_limit: int = Field(default=1, ge=0, le=100)
    enabled_extras: list[str] = Field(default_factory=list, max_length=100)
    disabled_tables: list[str] = Field(default_factory=list, max_length=100)
    excluded_rows: dict[str, list[str]] = Field(default_factory=dict, max_length=100)
    table_versions: dict[str, str] = Field(default_factory=dict, max_length=100)
    texture_tables: dict[str, str] = Field(default_factory=dict, max_length=5)


class RngUpdate(Input):
    expected_revision: int
    settings: RngSettings
    use_latest_tables: bool = False


class Attempt(Input):
    action: str = Field(min_length=1, max_length=3000)
    actor: str = Field(min_length=1, max_length=160)
    domain: str = Field(default="", max_length=160)
    level: int = Field(default=0, ge=-5, le=5)
    fractured: bool = False
    prepared: bool = False


class Beat(Input):
    label: str = Field(min_length=1, max_length=500)
    completed: bool = True
    waiting_for_player: bool = False
    protected: bool = False
    resolves_event: bool = False
    new_scene: bool = False
    family: Literal["narrative-push", "encounter", "none"] = "narrative-push"
    attempt: Attempt | None = None
    extras: list[str] = Field(default_factory=list, max_length=8)


class PrepareBeat(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    beat: Beat
    manual: bool = False
    reroll_of: str | None = None
    branch_name: str = Field(default="A different roll", min_length=1, max_length=120)


class TablePreview(Input):
    settings: RngSettings = Field(default_factory=RngSettings)
    seed: str = Field(default="preview", min_length=1, max_length=200)
