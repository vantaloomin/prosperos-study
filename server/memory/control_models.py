from typing import Literal

from pydantic import Field, model_validator

from server.models import Input

STANCES = {
    'knowledge': {'knows', 'believes', 'unaware', 'uncertain'},
    'conflict': {'unresolved', 'intentional', 'resolved'},
    'emphasis': {'pin', 'exclude', 'motif', 'avoid'},
}


class ControlEntry(Input):
    id: str = Field(min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    kind: Literal['knowledge', 'conflict', 'emphasis']
    subject: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=1200)
    stance: str
    enabled: bool = True
    character_id: str | None = Field(default=None, min_length=1, max_length=100)
    source_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def valid_stance(self):
        if self.character_id and self.kind != 'knowledge':
            raise ValueError('Only character knowledge can bind a Character identity.')
        if self.stance not in STANCES[self.kind]:
            raise ValueError('Choose a state that belongs to this author control.')
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError('Choose each evidence excerpt once.')
        if self.kind == 'conflict' and len(self.source_ids) < 2:
            raise ValueError('A conflict needs at least two source excerpts.')
        return self


class ControlSave(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    expected_version_id: str | None = None
    entries: list[ControlEntry] = Field(max_length=64)

    @model_validator(mode='after')
    def distinct_entries(self):
        if len({entry.id for entry in self.entries}) != len(self.entries):
            raise ValueError('Author control IDs must be distinct.')
        return self
