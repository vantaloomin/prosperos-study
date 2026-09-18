"""Versioned author choices and lexical cues, separate from world prose."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from server.errors import DomainError

SearchTerm = Annotated[str, Field(max_length=2000)]


class CanonCue(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    summary: str = Field(default='', max_length=32000)
    topics: list[SearchTerm] = Field(default_factory=list, max_length=256)
    aliases: list[SearchTerm] = Field(default_factory=list, max_length=256)


class CanonRecall(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    mode: Literal['full', 'relevant'] = 'full'
    cues: list[CanonCue] = Field(default_factory=list, max_length=5000)

    @model_validator(mode='after')
    def disjoint_spans(self):
        previous_end = 0
        for cue in sorted(self.cues, key=lambda cue: cue.start):
            if cue.end <= cue.start or cue.start < previous_end:
                raise ValueError('Search cue source spans must be nonempty and must not overlap.')
            previous_end = cue.end
        return self


def canon_policy(content):
    try:
        return CanonRecall.model_validate(content.get('canon_recall', {}))
    except ValidationError as error:
        raise DomainError('Canon recall: ' + error.errors()[0]['msg']) from error


def validate_canon(content):
    if 'canon_recall' in content:
        canon_policy(content)
