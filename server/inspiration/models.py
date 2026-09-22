from decimal import Decimal
from typing import Annotated

from pydantic import Field, StrictBool, StringConstraints, model_validator

from server.models import Input

CardId = Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$')]
Tag = Annotated[str, StringConstraints(min_length=1, max_length=60)]


def weight_units(value):
    return int(Decimal(str(value)) * 1_000_000)


class Card(Input):
    id: CardId
    title: str = Field(min_length=1, max_length=160)
    text: Annotated[str, StringConstraints(min_length=1, max_length=6000, strip_whitespace=False)]
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    weight: float = Field(default=1, strict=True, ge=0.000001, le=1_000_000, allow_inf_nan=False)
    enabled: StrictBool = True

    @model_validator(mode='after')
    def distinct_tags_and_exact_weight(self):
        if len(set(self.tags)) != len(self.tags):
            raise ValueError('Use each tag once per card; matching is case-sensitive.')
        scaled = Decimal(str(self.weight)) * 1_000_000
        if scaled != scaled.to_integral_value():
            raise ValueError('Card weights support at most six decimal places.')
        if not self.text.strip() or '\x00' in self.text:
            raise ValueError('Card text needs visible text without NUL characters.')
        return self


class DeckContent(Input):
    cards: list[Card] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def distinct_cards(self):
        if len({card.id for card in self.cards}) != len(self.cards):
            raise ValueError('Every card needs its own stable ID.')
        return self


class Filters(Input):
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    excluded_ids: list[CardId] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def distinct(self):
        if len(set(self.tags)) != len(self.tags) or len(set(self.excluded_ids)) != len(self.excluded_ids):
            raise ValueError('List each tag and exclusion once.')
        return self


class DeckCreate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=3000)
    content: DeckContent
    note: str = Field(default='', max_length=2000)
    unsupported: dict = Field(default_factory=dict)


class DeckPublish(DeckCreate):
    expected_version_id: str = Field(min_length=1, max_length=100)


class Preview(Input):
    content: DeckContent
    filters: Filters = Field(default_factory=Filters)
    seed: str = Field(default='preview', min_length=1, max_length=200)
    count: int = Field(default=5, strict=True, ge=1, le=100)


class Draw(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    filters: Filters = Field(default_factory=Filters)
    branch_id: str | None = Field(default=None, min_length=1, max_length=100)
    expected_revision: int | None = Field(default=None, strict=True, ge=0)

    @model_validator(mode='after')
    def branch_revision(self):
        if (self.branch_id is None) != (self.expected_revision is None):
            raise ValueError('A Story draw needs its selected path and current revision together.')
        return self
