from typing import Literal

from pydantic import Field

from server.models import Input

BatchKind = Literal['library', 'transcript', 'preset', 'archive', 'writing-bundle']


class BatchFile(Input):
    filename: str = Field(min_length=1, max_length=255)
    source_base64: str = Field(max_length=14 * 1024 * 1024)
    read_error: str = Field(default='', max_length=200)


class BatchUpload(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    files: list[BatchFile] = Field(min_length=1, max_length=20)


class BatchRevision(Input):
    expected_revision: int = Field(ge=0, strict=True)


class BatchResolve(BatchRevision):
    kind: BatchKind


class BatchPublish(BatchRevision):
    choices: dict


class BatchSkip(BatchRevision):
    skipped: bool


class BatchBundlePreview(Input):
    mappings: dict[str, str | None] = Field(default_factory=dict, max_length=128)
