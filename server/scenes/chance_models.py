from typing import Literal

from pydantic import Field

from server.mechanics.models import Attempt
from server.models import Input


class ChanceBoundary(Input):
    completed: bool = False
    waiting_for_player: bool = True
    protected: bool = False
    resolves_event: bool = False
    new_scene: bool = False
    family: Literal['narrative-push', 'encounter', 'none'] = 'narrative-push'
    attempt: Attempt | None = None
    extras: list[str] = Field(default_factory=list, max_length=8)
