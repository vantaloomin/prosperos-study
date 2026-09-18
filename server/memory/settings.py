from typing import Literal

from pydantic import Field, ValidationError

from server.errors import require
from server.memory.maintenance_models import MaintenanceSettings
from server.models import Input


class MemorySettings(Input):
    mode: Literal['full', 'long'] = 'full'
    recall_limit: int = Field(default=8, ge=1, le=16)
    open_threads: bool = True
    summary_recall: bool = False
    summary_context: bool = False
    maintenance: MaintenanceSettings = Field(default_factory=MaintenanceSettings)
    canon_limit: int = Field(default=8, ge=1, le=16)


def memory_settings(raw):
    try:
        return MemorySettings.model_validate(raw or {})
    except ValidationError:
        require(False, 'These story memory settings are invalid. Check Writing preferences.', 409)


def normalize_memory(settings):
    if 'memory' not in settings:
        return settings
    return {**settings, 'memory': memory_settings(settings['memory']).model_dump()}
