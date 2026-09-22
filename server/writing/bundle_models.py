from typing import Literal

from pydantic import ConfigDict, Field

from server.models import Input

MAX_BUNDLE = 8 * 1024 * 1024


class BundleItem(Input):
    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    kind: Literal['style', 'recipe']
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    note: str = Field(default='', max_length=2000)
    content: dict
    unsupported: dict = Field(default_factory=dict)


class BundleReference(Input):
    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    kind: Literal['model', 'table', 'style']
    name: str = Field(min_length=1, max_length=160)
    table_id: str | None = Field(default=None, max_length=100)


class Bundle(Input):
    model_config = ConfigDict(extra='allow', str_strip_whitespace=False)
    format: Literal['prospero-writing-bundle']
    version: Literal[1]
    root: str
    resources: list[BundleItem] = Field(min_length=1, max_length=32)
    references: list[BundleReference] = Field(default_factory=list, max_length=128)
    omitted_samples: int = Field(default=0, ge=0)
    unsupported: dict = Field(default_factory=dict)


class BundlePreview(Input):
    document: dict
    mappings: dict[str, str | None] = Field(default_factory=dict, max_length=128)


class BundleImport(BundlePreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_fingerprint: str = Field(min_length=64, max_length=64)


class BundleExport(Input):
    include_samples: bool = False
