"""Immutable, recoverable copies of original imports and converted documents."""
import json
from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from server.errors import require
from server.library_formats.files import SourceFiles, disk_hash, exclusive_write, source_io
from server.library_formats.import_conversion import source_bytes
from server.library_formats.png_cards import embedded_card


def package_files(row, conversion):
    suffix = {'card': 'json', 'png-card': 'png', 'markdown': 'md', 'sgc-brain': 'json'}[conversion['format']]
    report = {key: value for key, value in conversion.items() if key not in {'files', 'drafts'}}
    report['files'] = list(conversion['files'])
    original = source_bytes(row['source_base64'])
    extracted = {'source.json': embedded_card(original)[0]} if suffix == 'png' else {}
    return {f'source.{suffix}': original, **extracted,
            'conversion-report.json': json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'),
            **{f'converted/{key}': value.encode('utf-8') for key, value in conversion['files'].items()}}


def materialize_import(database, row, conversion):
    files = SourceFiles(database)
    folder = sha256(row['id'].encode()).hexdigest()
    with source_io():
        for relative, content in package_files(row, conversion).items():
            path = files.safe('imports', folder, relative)
            expected = sha256(content).hexdigest()
            if path.exists():
                require(disk_hash(path) == expected, 'A preserved import file changed on disk. Keep that edited copy separately before restoring this package.', 409)
            else:
                exclusive_write(path, content)
    return str(files.safe('imports', folder))


def package_zip(row, conversion):
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        for path, content in package_files(row, conversion).items():
            archive.writestr(path, content)
    return stream.getvalue()
