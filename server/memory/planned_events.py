"""Structured intentions inside accepted continuity; no clock or inference changes state."""
from typing import Literal, Self

from pydantic import Field, model_validator

from server.errors import require
from server.models import Input

CLOSED_PLAN_STATES = frozenset({'completed', 'cancelled'})


class PlanParticipant(Input):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=200)
    commitment: Literal['proposed', 'agreed', 'declined', 'withdrawn', 'uncertain']


class PlannedEvent(Input):
    status: Literal['proposed', 'agreed', 'postponed', 'attempted', 'uncertain', 'completed', 'cancelled']
    participants: list[PlanParticipant] = Field(min_length=1, max_length=24)
    timing: str = Field(min_length=1, max_length=500)
    time_anchor: str = Field(min_length=1, max_length=500)
    resolution: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def coherent_state(self) -> Self:
        ids = [person.id for person in self.participants]
        if len(set(ids)) != len(ids):
            raise ValueError('Each plan participant needs a unique, stable ID.')
        if (self.status in CLOSED_PLAN_STATES) != (self.resolution is not None):
            raise ValueError('Completed or cancelled plans need an explicit resolution; open plans have none.')
        return self


def validate_plan_update(change, target=None):
    """Validate an explicit proposed transition, never infer one from participant changes."""
    if change['kind'] != 'plan':
        return
    require(change['action'] != 'resolve',
            'Replace a plan with an explicit completed or cancelled status and supporting evidence.', 502)
    if target is None:
        return
    before = {person['id'] for person in target['plan']['participants']}
    after = {person['id'] for person in change['plan']['participants']}
    require(before <= after, 'Keep existing plan participants and record withdrawals or declines explicitly.', 502)


def plan_entry_fields(change):
    if change['kind'] != 'plan':
        return {}
    plan = change['plan']
    return {'plan': plan, 'status': 'resolved' if plan['status'] in CLOSED_PLAN_STATES else 'active'}
