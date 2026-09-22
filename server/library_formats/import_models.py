from typing import Literal

from pydantic import Field

from server.models import Input


class ImportUpload(Input):
    filename: str = Field(min_length=1, max_length=255)
    source_base64: str = Field(max_length=14 * 1024 * 1024)


class ImportChoice(Input):
    part: Literal['character', 'lorebook']
    name: str = Field(min_length=1, max_length=120)
    content: dict
    target_asset_id: str | None = None
    expected_version_id: str | None = None
    expected_source_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    duplicate_action: Literal['skip', 'new'] = 'skip'


class ImportPublish(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed_compatibility: bool
    choices: list[ImportChoice] = Field(min_length=1, max_length=2)
