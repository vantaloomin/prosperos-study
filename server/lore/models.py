from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from server.models import Input


class LoreEntry(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(default='', max_length=100000)
    enabled: bool = True
    kind: Literal['required', 'flavor'] = 'required'
    activation: Literal['always', 'keywords'] = 'keywords'
    keywords: list[str] = Field(default_factory=list, max_length=64)
    match: Literal['any', 'all'] = 'any'
    secondary: list[str] = Field(default_factory=list, max_length=64)
    secondary_mode: Literal['none', 'require', 'exclude'] = 'none'
    case_sensitive: bool = False
    whole_words: bool = True
    placement: Literal['header', 'recent', 'tail'] = 'recent'
    priority: int = Field(default=0, ge=-1000, le=1000)
    minimum_beats: int = Field(default=0, ge=0, le=10000)
    sticky_beats: int = Field(default=0, ge=0, le=1000)
    cooldown_beats: int = Field(default=0, ge=0, le=1000)
    chance_enabled: bool = False
    chance: int = Field(default=100, ge=0, le=100)

    @model_validator(mode='after')
    def coherent_rules(self):
        if not self.title.strip():
            raise ValueError('Give the entry a title.')
        for term in [*self.keywords, *self.secondary]:
            if not term.strip() or len(term) > 200:
                raise ValueError('Keywords must contain 1–200 characters.')
        if self.activation == 'keywords' and not self.keywords:
            raise ValueError('Add a keyword or choose Always.')
        if self.secondary_mode != 'none' and not self.secondary:
            raise ValueError('Add secondary keywords or turn the secondary condition off.')
        if self.kind == 'required' and (self.chance_enabled or self.cooldown_beats):
            raise ValueError('Required lore cannot be probabilistic or withheld by a cooldown.')
        return self


class LoreDefinition(Input):
    schema_version: Literal[1] = 1
    scan_messages: int = Field(default=12, ge=1, le=1000)
    flavor_budget_tokens: int = Field(default=1200, ge=0, le=1000000)
    entries: list[LoreEntry] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def unique_entries(self):
        if len({item.id for item in self.entries}) != len(self.entries):
            raise ValueError('Lore entry IDs must be unique within a book.')
        return self


class LorePreview(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    definition: LoreDefinition
    passage: str = Field(default='', max_length=100000)
    completed_beats: int = Field(default=0, ge=0, le=1000000)
    master_rng: bool = False
    seed: str = Field(default='lore-preview', min_length=1, max_length=200)
    prior_passages: list[Annotated[str, Field(max_length=100000)]] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def coherent_history(self):
        if self.completed_beats < len(self.prior_passages):
            raise ValueError('Completed beats must include all supplied prior passages.')
        return self
