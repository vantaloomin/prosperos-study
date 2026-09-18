from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Attachment(Input):
    asset_id: str
    version_id: str
    enabled: bool = True
    priority: int = 0


class OpeningSource(Input):
    asset_id: str = Field(min_length=1, max_length=100)
    version_id: str = Field(min_length=1, max_length=100)
    greeting_id: str = Field(min_length=1, max_length=100)


class StoryCreate(Input):
    operation_id: str | None = Field(default=None, min_length=8, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    premise: str = Field(default="", max_length=30000)
    opening_text: str = Field(default="", max_length=100000)
    opening_source: OpeningSource | None = None
    settings: dict = Field(default_factory=dict)
    attachments: list[Attachment] = Field(default_factory=list, max_length=100)


class StoryUpdate(Input):
    expected_revision: int
    title: str = Field(min_length=1, max_length=120)
    premise: str = Field(max_length=30000)
    settings: dict
    archived: bool = False


class MessageCreate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    text: str = Field(min_length=1, max_length=100000)
    role: Literal["user", "assistant", "narrator", "ooc"] = "user"
    opportunity_id: str | None = None


class ForkCreate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    node_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    replacement: str | None = Field(default=None, min_length=1, max_length=100000)


class PassageRevision(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    node_id: str
    action: Literal['remove', 'restore']
    name: str = Field(min_length=1, max_length=120)
    acknowledge_state_reset: Literal[True]


class AssetCreate(Input):
    kind: Literal["character", "lorebook", "persona"]
    name: str = Field(min_length=1, max_length=120)
    content: dict = Field(default_factory=dict)
    note: str = Field(default="", max_length=2000)


class AssetPublish(Input):
    expected_version_id: str
    expected_source_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    expected_entry_hashes: dict[str, str] = Field(default_factory=dict, max_length=500)
    name: str = Field(min_length=1, max_length=120)
    content: dict
    note: str = Field(default="", max_length=2000)


class VersionLookup(Input):
    version_ids: list[str] = Field(max_length=200)


class AdoptionTarget(Input):
    story_id: str
    expected_revision: int
    manifest_id: str


class AdoptionPreviewRequest(Input):
    additional_version_ids: list[str] = Field(default_factory=list, max_length=32)


class AdoptionApply(AdoptionPreviewRequest):
    operation_id: str = Field(min_length=8, max_length=100)
    targets: list[AdoptionTarget]
    preview_hash: str | None = None


class AttachmentUpdate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int
    attachments: list[Attachment] = Field(max_length=100)
