from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from server.models import Input


class PresetUpload(Input):
    filename: str = Field(min_length=1, max_length=255)
    source_base64: str = Field(max_length=1400000)


class PresetConfiguration(Input):
    sampling_keys: list[str] = Field(default_factory=list, max_length=8)
    base_profile_id: str | None = None
    expected_profile_version_id: str | None = None


class PresetPublish(PresetConfiguration):
    operation_id: str = Field(min_length=8, max_length=100)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]
    duplicate_action: Literal['skip', 'new'] = 'skip'
    name: str = Field(min_length=1, max_length=120)
    instructions: Annotated[str, StringConstraints(strip_whitespace=False, max_length=12000)] = ''
    instruction_keys: list[str] = Field(default_factory=list, max_length=133)
    target_asset_id: str | None = None
    expected_version_id: str | None = None
