from server.archives.library_sources import lore_versions
from server.errors import require
from server.library_formats.files import read_markdown, source_io
from server.library_formats.sources import MAX_MARKDOWN_BYTES
from server.lore.documents import entry_sources
from server.lore.files import EntryFiles


def collect_entry_drafts(database, data):
    result = {}
    for version in lore_versions(data):
        changed = {}
        for source in entry_sources(version):
            path = EntryFiles(database, source['entry_id']).working_path(version['asset_id'], version['id'])
            with source_io():
                text = read_markdown(path) if path.exists() else None
            if text != source['markdown']:
                changed[source['entry_id']] = text
        if changed:
            result[version['id']] = changed
    return result


def validate_entry_sources(document):
    versions = {row['id']: row for row in lore_versions(document['data'])}
    require(set(document['lore_drafts']) <= set(versions), 'Entry working files reference a missing book version.')
    for version in versions.values():
        sources = {item['entry_id']: item for item in entry_sources(version)}
        changed = document['lore_drafts'].get(version['id'], {})
        require(set(changed) <= set(sources), 'An entry working file references an unknown entry.')
        for text in changed.values():
            require(text is None or len(text.encode('utf-8')) <= MAX_MARKDOWN_BYTES, 'An entry working file exceeds 10 MiB.')


def restore_entry_sources(database, document, mapping):
    for version in lore_versions(document['data']):
        changed = document['lore_drafts'].get(version['id'], {})
        for source in entry_sources(version):
            files = EntryFiles(database, source['entry_id'])
            restored = {**source, 'version_id': mapping[version['id']]}
            text = changed.get(source['entry_id'], source['markdown'])
            if text is None:
                with source_io():
                    files.ensure_snapshot(restored)
            else:
                files.materialize(restored, mapping[version['asset_id']], working=text)
