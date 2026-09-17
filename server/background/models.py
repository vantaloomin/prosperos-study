from pydantic import Field, model_validator

from server.models import Input


class Preparation(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    character_ids: list[str] = Field(default_factory=list, max_length=30)
    hooks: int = Field(default=0, ge=0, le=8)
    origin: str = Field(default='Story opening', min_length=1, max_length=200)
    day: int = Field(default=0, ge=0, le=1000000)
    horizon: int = Field(default=30, ge=1, le=3650)
    reroll_of: str | None = None
    branch_name: str = Field(default='Another background', min_length=1, max_length=120)

    @model_validator(mode='after')
    def selection(self):
        if not self.reroll_of and not (self.character_ids or self.hooks):
            raise ValueError('Choose supporting characters, future hooks, or both.')
        if len(set(self.character_ids)) != len(self.character_ids):
            raise ValueError('Choose each supporting character once.')
        return self


class BackgroundUpdate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    drives_enabled: bool
    hooks_enabled: bool
    day: int = Field(ge=0, le=1000000)
