from pathlib import Path

from pydantic import Field, field_validator

from server.models import Input


class BackupSettings(Input):
    expected_revision: int = Field(ge=0)
    enabled: bool = False
    interval_minutes: int = Field(default=1440, ge=15, le=43200)
    keep_count: int = Field(default=10, ge=1, le=365)
    destination: str = Field(default='', max_length=2000)
    include_sidebar: bool = False

    @field_validator('destination')
    @classmethod
    def absolute_directory(cls, value):
        if value and ('\x00' in value or not Path(value).is_absolute()):
            raise ValueError('Choose an absolute folder path, or leave it blank for the default folder.')
        return value


class BackupNow(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
