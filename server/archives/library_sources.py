"""Archive published Markdown and separately preserve unpublished file edits."""
from server.archives.records import related_rows
from server.database import decode
from server.errors import require
from server.library_formats.files import SourceFiles, read_markdown, source_io
from server.library_formats.sources import MAX_MARKDOWN_BYTES, source_record, validate_source
from server.memory.canon_models import validate_canon


def lore_versions(data):
    kinds = {row['id']: row['kind'] for row in data['assets']}
    return [version for version in data['asset_versions'] if kinds[version['asset_id']] == 'lorebook']


def collect_sources(connection, data):
    sources = {row['version_id']: row for row in related_rows(connection, 'asset_sources', 'version_id', {row['id'] for row in lore_versions(data)})}
    data['asset_sources'] = [sources.get(version['id']) or source_record(version) for version in lore_versions(data)]


def collect_drafts(database, data):
    files, result = SourceFiles(database), {}
    for version in lore_versions(data):
        source = source_record(version)
        path = files.working_path(version['asset_id'], version['id'])
        with source_io():
            text = read_markdown(path) if path.exists() else None
        if text != source['markdown']:
            result[version['id']] = text
    return result


def validate_sources(document):
    data = document['data']
    versions = {row['id']: row for row in lore_versions(data)}
    require({row['version_id'] for row in data['asset_sources']} == set(versions),
            'The archive must include Markdown sources for every lorebook version.')
    for version in versions.values():
        validate_canon(decode(version['content']))
    for source in data['asset_sources']:
        validate_source(source, versions[source['version_id']])
    for key, text in document['library_drafts'].items():
        require(key in versions, 'A working Markdown file refers to a missing lorebook version.')
        require(text is None or len(text.encode('utf-8')) <= MAX_MARKDOWN_BYTES, 'A working Markdown file exceeds 10 MiB.')


def restore_sources(database, connection, document, mapping):
    files = SourceFiles(database)
    for version in lore_versions(document['data']):
        restored = {**version, 'id': mapping[version['id']], 'asset_id': mapping[version['asset_id']]}
        # Plain Markdown has no structural workspace IDs. Legacy non-text data uses its remapped index.
        row = connection.execute('SELECT content FROM asset_versions WHERE id=?', (restored['id'],)).fetchone()
        restored['content'] = decode(row['content'])
        source = source_record(restored)
        draft = document['library_drafts'].get(version['id'], source['markdown'])
        if draft is None:
            with source_io():
                files.ensure_snapshot(source)
        else:
            files.materialize(source, restored['asset_id'], working=draft)
