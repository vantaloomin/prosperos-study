from hashlib import sha256

from server.database import one
from server.errors import require
from server.library_formats.files import SourceFiles, disk_hash, read_markdown, source_io
from server.library_formats.service import MarkdownLibrary
from server.library_formats.sources import source_hash
from server.lore.documents import entry_sources, parse_entry


class EntryFiles(SourceFiles):
    def __init__(self, database, entry_id):
        super().__init__(database)
        self.entry_id = entry_id

    def working_path(self, asset_id, version_id):
        book = super().working_path(asset_id, version_id)
        return self.safe(*book.parent.relative_to(self.root).parts, 'entries', sha256(self.entry_id.encode()).hexdigest() + '.md')

    def source(self, connection, asset_id, version_id):
        version = one(connection, 'SELECT v.*,a.kind FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE v.id=?', (version_id,))
        require(version['asset_id'] == asset_id and version['kind'] == 'lorebook', 'Choose a lorebook version.')
        source = next((item for item in entry_sources(version) if item['entry_id'] == self.entry_id), None)
        require(source is not None, 'This entry does not belong to that published version.', 404)
        return source

    def view(self, connection, asset_id, version_id):
        source = self.source(connection, asset_id, version_id)
        return self.view_source(source, asset_id)

    def view_source(self, source, asset_id):
        path = self.working_path(asset_id, source['version_id'])
        with source_io():
            text = read_markdown(path) if path.exists() else None
            snapshot = self.object_path(source['sha256'])
            snapshot_hash = disk_hash(snapshot) if snapshot.exists() else None
        return {**source, 'file_path': str(path), 'markdown': text,
                'sha256': source_hash(text) if text is not None else None,
                'published_sha256': source['sha256'], 'missing': text is None,
                'changed': text is not None and source_hash(text) != source['sha256'],
                'snapshot_hash': snapshot_hash, 'snapshot_needs_recovery': snapshot_hash != source['sha256']}

    def check(self, version, published, hashes):
        source = self.view_source(published, version['asset_id'])
        require(not source['missing'], f"Recover the missing entry file for {source['title']} before publishing.", 409)
        require(source['sha256'] == (hashes.get(self.entry_id) or source['published_sha256']),
                f"The entry file for {source['title']} changed. Review it in Entry Markdown files before publishing.", 409)


def stage_entries(database, version):
    for source in entry_sources(version):
        EntryFiles(database, source['entry_id']).materialize(source, version['asset_id'])


def check_entries(connection, database, version, hashes):
    for source in entry_sources(version):
        EntryFiles(database, source['entry_id']).check(version, source, hashes)


class EntryLibrary:
    def __init__(self, database):
        self.database = database

    def view(self, version_id):
        with self.database.connect() as connection:
            version = one(connection, 'SELECT * FROM asset_versions WHERE id=?', (version_id,))
            return [EntryFiles(self.database, item['entry_id']).view_source(item, version['asset_id'])
                    for item in entry_sources(version)]

    def read(self, version_id, entry_id):
        with self.database.connect() as connection:
            version = one(connection, 'SELECT * FROM asset_versions WHERE id=?', (version_id,))
            files = EntryFiles(self.database, entry_id)
            return files, files.source(connection, version['asset_id'], version_id), version

    def download(self, version_id, entry_id):
        files, source, _version = self.read(version_id, entry_id)
        with source_io():
            files.ensure_snapshot(source)
        return source

    def proposal(self, version_id, entry_id):
        files, _source, version = self.read(version_id, entry_id)
        with self.database.connect() as connection:
            view = files.view(connection, version['asset_id'], version_id)
        require(not view['missing'], 'Recover the missing entry file before reviewing it.', 409)
        return {**view, 'entry': parse_entry(view['markdown'], entry_id).model_dump()}

    def recover(self, version_id, entry_id, body):
        require(body.version_id == version_id, 'Choose the same version as this recovery preview.')
        files, source, version = self.read(version_id, entry_id)
        service = MarkdownLibrary(self.database)
        service.files = files
        with self.database.connect(write=True) as connection, source_io():
            retained = service.recover_file(version['asset_id'], source, body)
            return {**files.view(connection, version['asset_id'], version_id), 'retained_file': retained}
