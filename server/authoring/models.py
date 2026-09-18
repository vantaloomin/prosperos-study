from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from server.models import Input

Prose = Annotated[str, StringConstraints(strip_whitespace=False, max_length=100000)]
ContextKey = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class AuthoringPreview(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    source_version_id: str | None = None
    draft_id: str = Field(min_length=1, max_length=100)
    kind: Literal['character', 'lorebook', 'persona']
    name: str = Field(max_length=160)
    target_key: str = Field(min_length=1, max_length=200)
    target_label: str = Field(min_length=1, max_length=200)
    text: Prose
    context: dict[ContextKey, Prose] = Field(default_factory=dict, max_length=30)
    direction: str = Field(default='', max_length=10000)
    step: Literal['authoring-draft', 'authoring-critique', 'authoring-tighten', 'authoring-enrich']
    profile_ids: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def bounded_context(self):
        if sum(len(key.encode('utf-8')) + len(value.encode('utf-8')) for key, value in self.context.items()) > 1024 * 1024:
            raise ValueError('Authoring context is limited to 1 MiB; select fewer supporting fields.')
        return self


class AuthoringStart(AuthoringPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


class Finding(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    quote: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=4000)
    suggestion: str = Field(min_length=1, max_length=4000)


class AuthoringOutput(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    summary: str = Field(min_length=1, max_length=6000)
    proposal: Prose | None
    findings: list[Finding] = Field(default_factory=list, max_length=10)


class AuthoringDefault(Input):
    step: Literal['authoring-draft', 'authoring-critique', 'authoring-tighten', 'authoring-enrich']
    profile_id: str | None = None
