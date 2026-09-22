from typing import Literal

from pydantic import ConfigDict, Field

from server.models import Input


class PackDeck(Input):
    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)
    key: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$')
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=3000)
    content: dict
    unsupported: dict = Field(default_factory=dict)


class Pack(Input):
    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)
    format: Literal['prospero-inspiration-pack']
    version: Literal[1]
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=3000)
    decks: list[PackDeck] = Field(min_length=1, max_length=32)
    unsupported: dict = Field(default_factory=dict)


class PackUpload(Input):
    filename: str = Field(min_length=1, max_length=255)
    source_base64: str = Field(min_length=1, max_length=12 * 1024 * 1024)


class PackChoice(Input):
    key: str = Field(min_length=1, max_length=80)
    duplicate_action: Literal['skip', 'new'] = 'skip'
    target_deck_id: str | None = None
    expected_version_id: str | None = None


class PackImport(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]
    choices: list[PackChoice] = Field(min_length=1, max_length=32)


class PackExport(Input):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=3000)
    version_ids: list[str] = Field(min_length=1, max_length=32)
