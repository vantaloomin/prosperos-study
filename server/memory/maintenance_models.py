from pydantic import Field

from server.models import Input


class MaintenanceSettings(Input):
    enabled: bool = False
    batch_size: int = Field(default=4, ge=1, le=8)
    max_batches: int = Field(default=1, ge=1, le=4)


class BackfillPreview(Input):
    expected_revision: int = Field(ge=0)
    batch_size: int = Field(default=4, ge=1, le=8)
    max_batches: int = Field(default=1, ge=1, le=4)
    profile_ids: list[str] = Field(default_factory=list, max_length=4)


class BackfillStart(BackfillPreview):
    operation_id: str = Field(min_length=8, max_length=100)
    preview_hash: str = Field(min_length=64, max_length=64)


class MaintenanceResume(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)


class BatchResume(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_status: str = Field(min_length=1, max_length=20)
