"""Content-addressed snapshots and per-version working files.

Files are staged before the database commit. An interrupted write can leave an
unreferenced file, never a visible version with a partially written source.
Working files are never replaced on publication, including concurrent edits.
"""
import os
from contextlib import contextmanager
from hashlib import sha256
from uuid import uuid4

from server.database import decode, many, one
from server.errors import DomainError, require
from server.library_formats.sources import MAX_MARKDOWN_BYTES, source_hash, source_record


@contextmanager
def source_io():
    try:
        yield
    except (OSError, UnicodeError) as error:
        raise DomainError('The Markdown file could not be read or saved. Check its location, permissions and UTF-8 encoding; your published version is unchanged.', 503) from error


def exclusive_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{uuid4().hex}.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(content.encode('utf-8') if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == 'nt':
            temporary.rename(path)  # Windows rename fails if the destination exists.
        else:
            os.link(temporary, path)  # Exclusive, atomic creation on POSIX.
    finally:
        temporary.unlink(missing_ok=True)


def read_markdown(path):
    with path.open('rb') as stream:
        content = stream.read(MAX_MARKDOWN_BYTES + 1)
    require(len(content) <= MAX_MARKDOWN_BYTES, 'Use at most 10 MiB of Markdown per working file.')
    return content.decode('utf-8')


def disk_hash(path):
    digest = sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class SourceFiles:
    def __init__(self, database):
        self.root = database.path.parent.resolve() / f'{database.path.stem}-library'

    def safe(self, *parts):
        path = self.root.joinpath(*parts)
        require(path.resolve().is_relative_to(self.root.resolve()), 'The Markdown path leaves this Library.')
        return path

    def object_path(self, digest):
        require(len(digest) == 64 and all(char in '0123456789abcdef' for char in digest), 'Invalid Markdown hash.')
        return self.safe('objects', digest + '.md')

    def working_path(self, asset_id, version_id):
        asset = sha256(asset_id.encode()).hexdigest()
        version = sha256(version_id.encode()).hexdigest()
        return self.safe('books', asset, version, 'book.md')

    def ensure_snapshot(self, source):
        path = self.object_path(source['sha256'])
        require(source_hash(source['markdown']) == source['sha256'], 'The saved Markdown recovery copy is inconsistent.')
        if path.exists():
            require(disk_hash(path) == source['sha256'],
                    'A published Markdown snapshot changed on disk. Recover it from the Library source panel.', 409)
        else:
            exclusive_write(path, source['markdown'])
        return path

    def materialize(self, source, asset_id, keep_working=False, working=None):
        with source_io():
            self.ensure_snapshot(source)
            path = self.working_path(asset_id, source['version_id'])
            if not (keep_working and path.exists()):
                require(not path.exists(), 'This working file already exists; no file was overwritten.', 409)
                exclusive_write(path, source['markdown'] if working is None else working)

    def stage(self, connection, version, keep_working=False):
        source = source_record(version)
        self.materialize(source, version['asset_id'], keep_working)
        connection.execute('INSERT INTO asset_sources VALUES (?,?,?,?)', tuple(source.values()))
        return source

    def view(self, connection, asset_id, version_id):
        version = one(connection, 'SELECT v.*,a.kind FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE v.id=?', (version_id,))
        require(version['asset_id'] == asset_id and version['kind'] == 'lorebook', 'Choose a lorebook version.')
        source = one(connection, 'SELECT * FROM asset_sources WHERE version_id=?', (version_id,))
        path = self.working_path(asset_id, version_id)
        with source_io():
            text = read_markdown(path) if path.exists() else None
            snapshot = self.object_path(source['sha256'])
            snapshot_hash = disk_hash(snapshot) if snapshot.exists() else None
        return {'version_id': version_id, 'format': source['format'], 'file_path': str(path),
                'markdown': text, 'sha256': source_hash(text) if text is not None else None,
                'published_sha256': source['sha256'], 'missing': text is None,
                'snapshot_hash': snapshot_hash, 'snapshot_needs_recovery': snapshot_hash != source['sha256'],
                'changed': text is not None and source_hash(text) != source['sha256']}

    def check_edit(self, connection, asset_id, version_id, expected_hash):
        source = self.view(connection, asset_id, version_id)
        require(not source['missing'], 'The working Markdown file is missing. Recover it in Markdown source before publishing.', 409)
        require(source['sha256'] == (expected_hash or source['published_sha256']),
                'The Markdown file changed outside this editor. Review it in Markdown source before publishing; your draft is preserved.', 409)


def migrate_sources(database):
    files = SourceFiles(database)
    with database.connect(write=True) as connection:
        rows = many(connection, 'SELECT v.* FROM asset_versions v JOIN assets a ON a.id=v.asset_id '
                    'LEFT JOIN asset_sources s ON s.version_id=v.id WHERE a.kind=? AND s.version_id IS NULL', ('lorebook',))
        for row in rows:
            files.stage(connection, {**row, 'content': decode(row['content'])}, keep_working=True)
