"""Bounded source inspection; valid ambiguous interpretations remain author choices."""
import json
from hashlib import sha256
from pathlib import PureWindowsPath

from server.archives.format import canonical, summary
from server.archives.validate import parse_archive
from server.errors import DomainError, require
from server.library_formats.import_conversion import convert_import, source_bytes
from server.library_formats.import_duplicates import proposal_hash
from server.library_formats.markdown import read_json
from server.migration.preset_conversion import convert_preset
from server.migration.transcript_conversion import convert_transcript
from server.writing.bundles import bundle_items, read_bundle

MAX_BATCH_BYTES = 32 * 1024 * 1024


def hash_value(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reader_name(filename, suffix):
    path = PureWindowsPath(filename)
    return filename if path.suffix.lower() == suffix else path.stem[:240] + suffix


def intended_readers(filename, source):
    if source.startswith((b'PK\x03\x04', b'\x89PNG\r\n\x1a\n')):
        suffix = '.png' if source.startswith(b'\x89PNG') else PureWindowsPath(filename).suffix.lower()
        return [('library', reader_name(filename, suffix or '.zip'))]
    text = source.decode('utf-8-sig')
    stripped = text.lstrip()
    if stripped.startswith(('{', '[')):
        try:
            value = read_json(text)
        except ValueError:
            first = read_json(next((line for line in text.splitlines() if line.strip()), ''))
            if isinstance(first, dict) and {'chat_metadata', 'user_name', 'character_name'} & set(first):
                return [('transcript', reader_name(filename, '.jsonl'))]
            raise
        if isinstance(value, dict) and value.get('format') in ('roleplay-archive', 'prospero-writing-bundle'):
            return [('archive' if value['format'] == 'roleplay-archive' else 'writing-bundle', filename)]
        return [(kind, reader_name(filename, '.json')) for kind in ('library', 'transcript', 'preset')]
    require(PureWindowsPath(filename).suffix.lower() in {'.txt', '.md', '.markdown'}, 'No supported content signature was found. Plain text needs a .txt or Markdown extension.')
    return [('transcript', reader_name(filename, '.txt')), ('library', reader_name(filename, '.md'))]


def inspect_reader(kind, filename, source):
    if kind == 'library':
        report = convert_import(filename, source)
        return {'label': report.get('format_label', report['format']), 'proposals': {item['part']: proposal_hash(item) for item in report['drafts']}}
    if kind == 'transcript':
        report = convert_transcript(filename, source)
        return {'label': report['format'], 'proposals': {'transcript': report['content_sha256']}}
    if kind == 'preset':
        report = convert_preset(filename, source)
        return {'label': report['format'], 'proposals': {'preset': report['content_sha256']}}
    if kind == 'archive':
        document = parse_archive(source.decode('utf-8-sig'))
        return {'label': f"Study archive · {summary(document)['title']}", 'proposals': {'archive': sha256(canonical(document).encode()).hexdigest()}}
    document = read_json(source.decode('utf-8-sig'))
    bundle = read_bundle(document)
    bundle_items(bundle)
    return {'label': 'Study writing bundle', 'proposals': {'writing-bundle': hash_value(document)}}


def inspect_file(body):
    source = source_bytes(body.source_base64)
    candidates, errors = {}, []
    for kind, filename in intended_readers(body.filename, source):
        try:
            candidates[kind] = {'filename': filename, **inspect_reader(kind, filename, source)}
        except (DomainError, ValueError, UnicodeError) as error:
            errors.append(str(error))
    require(bool(candidates), 'No supported interpretation: ' + ' · '.join(dict.fromkeys(errors))[:1500])
    return {'source_sha256': sha256(source).hexdigest(), 'candidates': candidates}
