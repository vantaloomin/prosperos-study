from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from server.models import Input
from server.writing.models import Sample

StyleField = Literal['prose', 'viewpoint', 'tense', 'dialogue', 'rhythm', 'description', 'avoid']


class AnalysisPreview(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    draft_id: str = Field(min_length=8, max_length=100)
    source_version_id: str | None = None
    name: str = Field(default='', max_length=120)
    samples: list[Sample] = Field(min_length=1, max_length=8)
    profile_id: str | None = None

    @model_validator(mode='after')
    def nonempty_samples(self):
        if any(not sample.text.strip() or not sample.label.strip() for sample in self.samples):
            raise ValueError('Select samples with both a label and nonempty writing.')
        return self


class AnalysisStart(AnalysisPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class AnalysisEvidence(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    sample_id: str = Field(min_length=1, max_length=20)
    quote: str = Field(min_length=1, max_length=2000)


class StyleSuggestion(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    field: StyleField
    value: str = Field(min_length=1, max_length=12000)
    reason: str = Field(min_length=1, max_length=2000)
    evidence: list[AnalysisEvidence] = Field(min_length=1, max_length=4)


class AnalysisOutput(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    summary: str = Field(min_length=1, max_length=4000)
    suggestions: list[StyleSuggestion] = Field(max_length=7)

    @model_validator(mode='after')
    def distinct_fields(self):
        fields = [item.field for item in self.suggestions]
        if len(fields) != len(set(fields)):
            raise ValueError('Return each style field at most once.')
        if any(not item.value.strip() or not item.reason.strip() for item in self.suggestions):
            raise ValueError('Style suggestions need nonempty guidance and reasons.')
        return self
