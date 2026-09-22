from typing import Literal

from pydantic import Field

from server.models import Input


class TranscriptUpload(Input):
    filename: str = Field(min_length=1, max_length=255)
    source_base64: str = Field(max_length=14 * 1024 * 1024)


class MessageSelection(Input):
    index: int = Field(ge=0, lt=2000, strict=True)
    variant: int = Field(ge=0, le=100, strict=True)
    role: Literal['user', 'assistant', 'narrator', 'ooc']


class TranscriptPublish(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    title: str = Field(min_length=1, max_length=120)
    reviewed: Literal[True]
    duplicate_action: Literal['skip', 'new'] = 'skip'
    selections: list[MessageSelection] = Field(min_length=1, max_length=2000)
