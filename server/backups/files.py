import os
from pathlib import Path

from server.archives.format import MAX_ARCHIVE_BYTES, digest
from server.errors import DomainError, require


def directory_for(database, settings):
    root = Path(settings['destination']) if settings['destination'] else database.path.parent
    return root.absolute() / f"prosperos-backups-{settings['workspace_id']}"


def run_path(run):
    identity = run['id']
    require(len(identity) == 32 and all(char in '0123456789abcdef' for char in identity),
            'Invalid saved backup identifier.')
    directory = Path(run['directory'])
    require(directory.name == f"prosperos-backups-{run['settings']['workspace_id']}",
            'This backup directory does not belong to the workspace.', 409)
    require(not directory.is_symlink() and directory.resolve() == directory.absolute(),
            'The backup directory moved or became a link. Choose a regular folder and try again.', 409)
    target = directory / f'{identity}.json'
    require(not target.is_symlink() and target.resolve().parent == directory.resolve(),
            'The saved backup path changed. Import a separate trusted copy.', 409)
    return target


def write_archive(run, content):
    target = run_path(run)
    require(target.parent.parent.is_dir(), 'The destination folder is unavailable. Reconnect it or choose another folder.')
    target.parent.mkdir(exist_ok=True)
    require(not target.exists(), 'This backup file already exists. Create another copy.', 409)
    temporary = target.with_suffix('.partial')
    raw = content.encode('utf-8')
    require(len(raw) <= MAX_ARCHIVE_BYTES, 'This workspace exceeds the private archive size limit.')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Read back the saved bytes before exposing the file as complete.
        require(temporary.read_bytes() == raw, 'The saved backup could not be verified. Try another destination.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def read_archive(run):
    require(run['status'] == 'ready', 'This backup is not a complete saved copy.', 409)
    target = run_path(run)
    require(target.is_file(), 'This backup is unavailable. Reconnect its destination or choose another copy.', 404)
    require(target.stat().st_size <= MAX_ARCHIVE_BYTES, 'This saved backup exceeds the archive size limit.', 409)
    content = target.read_bytes().decode('utf-8')
    require(digest(content) == run['sha256'], 'The saved backup changed. Import and review a separate trusted copy.', 409)
    return content


def availability(run):
    if run['status'] != 'ready':
        return False
    try:
        return run_path(run).is_file()
    except (OSError, ValueError, DomainError):
        return False
