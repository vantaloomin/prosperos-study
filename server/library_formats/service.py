from uuid import uuid4

from pydantic import Field

from server.database import one
from server.errors import require
from server.library_formats.files import SourceFiles, disk_hash, exclusive_write, source_io
from server.models import Input


class SourceRecovery(Input):
    version_id: str
    target: str = Field(pattern=r'^(working|published)$')
    expected_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class MarkdownLibrary:
    def __init__(self, database):
        self.database = database
        self.files = SourceFiles(database)

    def view(self, asset_id, version_id=None):
        with self.database.connect() as connection:
            asset = one(connection, 'SELECT * FROM assets WHERE id=?', (asset_id,))
            return self.files.view(connection, asset_id, version_id or asset['latest_version_id'])

    def download(self, version_id):
        with self.database.connect() as connection:
            source = one(connection, 'SELECT s.*,v.name FROM asset_sources s JOIN asset_versions v ON v.id=s.version_id WHERE s.version_id=?', (version_id,))
        with source_io():
            path = self.files.ensure_snapshot(source)
        return source, path

    def recover(self, asset_id, body):
        with self.database.connect(write=True) as connection:
            self.files.view(connection, asset_id, body.version_id)
            source = one(connection, 'SELECT * FROM asset_sources WHERE version_id=?', (body.version_id,))
            with source_io():
                retained = self.recover_file(asset_id, source, body)
            return {**self.files.view(connection, asset_id, body.version_id), 'retained_file': retained}

    def recover_file(self, asset_id, source, body):
        path = self.files.working_path(asset_id, body.version_id) if body.target == 'working' else self.files.object_path(source['sha256'])
        current = disk_hash(path) if path.exists() else None
        require(current == body.expected_hash, 'The file changed after this recovery preview. Refresh before recovering.', 409)
        require(body.target != 'working' or current is None, 'Working files are recovered only when missing; existing edits are never replaced.', 409)
        retained = None
        if path.exists():
            retained = self.files.safe('recovered-edits', f'{uuid4().hex}.md')
            retained.parent.mkdir(parents=True, exist_ok=True)
            path.rename(retained)
        exclusive_write(path, source['markdown'])
        return str(retained) if retained else None
