"""Bounded, read-only ZIP inspection. Imported paths are never filesystem targets."""
import stat
import zlib
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from server.library_formats.cards import MAX_SOURCE_BYTES
from server.library_formats.markdown import read_json

MAX_CONTAINER_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 256


def safe_member(name):
    if not isinstance(name, str) or not name or len(name) > 240:
        raise ValueError('Container paths must have 1–240 characters.')
    parts = name.rstrip('/').split('/')
    if any(part in {'', '.', '..'} or part.endswith((' ', '.')) for part in parts):
        raise ValueError('Container paths must be relative and cannot contain traversal or ambiguous segments.')
    if any(ord(char) < 32 or char in '<>:"\\|?*' for char in name):
        raise ValueError('Container paths must use portable forward-slash names without drive paths or control characters.')
    return name.rstrip('/')


def checked_members(archive):
    members, seen, total = [], set(), 0
    entries = archive.infolist()
    if len(entries) > MAX_MEMBERS:
        raise ValueError('Character containers are limited to 256 entries.')
    for entry in entries:
        name = safe_member(entry.orig_filename)
        if name.casefold() in seen:
            raise ValueError('Container paths must be unique, including letter case.')
        seen.add(name.casefold())
        mode = stat.S_IFMT(entry.external_attr >> 16)
        if entry.flag_bits & 1 or mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError('Encrypted containers, links and special files are unsupported.')
        if entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            raise ValueError('Use stored or deflated ZIP entries.')
        total += entry.file_size
        if entry.file_size > MAX_SOURCE_BYTES or total > MAX_CONTAINER_BYTES:
            raise ValueError('Container entries are limited to 10 MiB each and 32 MiB expanded in total.')
        if not entry.is_dir():
            members.append(entry)
    return members


def read_container(source):
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Character containers are limited to 10 MiB per file.')
    try:
        with ZipFile(BytesIO(source)) as archive:
            result = {}
            for entry in checked_members(archive):
                with archive.open(entry) as stream:
                    raw = stream.read(MAX_SOURCE_BYTES + 1)
                if len(raw) != entry.file_size or len(raw) > MAX_SOURCE_BYTES:
                    raise ValueError('A container entry does not match its declared size.')
                result[entry.filename] = raw
            return result
    except (BadZipFile, RuntimeError, OSError, NotImplementedError, zlib.error) as error:
        raise ValueError('This character container is damaged or uses an unsupported ZIP encoding.') from error


def member_json(members, path):
    safe_member(path)
    if path not in members:
        raise ValueError(f'The container is missing its declared document: {path}.')
    value = read_json(members[path].decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'{path} must contain a JSON object.')
    return value


def convert_container(source):
    from server.library_formats.byaf import convert_byaf
    from server.library_formats.charx import convert_charx

    members = read_container(source)
    if ('card.json' in members) == ('manifest.json' in members):
        raise ValueError('Choose a CHARX with a root card.json or a BYAF v1 with a root manifest.json; ambiguous containers need review.')
    return convert_charx(source, members) if 'card.json' in members else convert_byaf(source, members)


def asset_member(source, conversion, index):
    assets = conversion.get('assets', [])
    if not 0 <= index < len(assets) or not assets[index].get('path'):
        raise ValueError('This asset is not an embedded file in the preserved container.')
    path = assets[index]['path']
    members = read_container(source)
    if path not in members:
        raise ValueError('This referenced asset is missing from the container.')
    return PurePosixPath(path).name, members[path]
