"""Native entry Markdown is preserved alongside its validated, versioned index."""
from pydantic import ValidationError

from server.database import decode
from server.errors import DomainError, require
from server.library_formats.markdown import document, read_document
from server.library_formats.sources import MAX_MARKDOWN_BYTES, source_hash
from server.lore.models import LoreDefinition, LoreEntry


def definition(content):
    try:
        return LoreDefinition.model_validate(content.get('lore_definition', {}))
    except ValidationError as error:
        raise DomainError('Lore rules: ' + error.errors()[0]['msg']) from error


def entry_markdown(entry):
    return document({'kind': 'native-lore-entry', 'entry': entry.model_dump(exclude={'text'})}, entry.text)


def parse_entry(markdown, entry_id):
    try:
        metadata, prose = read_document(markdown)
        require(metadata.get('kind') == 'native-lore-entry', 'Keep this entry’s native Markdown metadata header.')
        entry = LoreEntry.model_validate({**metadata.get('entry', {}), 'text': prose})
        require(entry.id == entry_id, 'The entry ID changed. Keep the original ID when editing its file.')
        return entry
    except (ValueError, TypeError) as error:
        raise DomainError('Invalid entry Markdown: ' + str(error)) from error


def retained_document(entry, documents):
    text = documents.get(entry.id)
    if isinstance(text, str):
        try:
            if parse_entry(text, entry.id) == entry:
                return text
        except DomainError:
            pass
    return entry_markdown(entry)


def normalize_lore(content):
    if 'lore_definition' not in content:
        require('lore_documents' not in content, 'Entry documents need their lore definition.')
        return content
    parsed = definition(content)
    existing = content.get('lore_documents', {})
    require(isinstance(existing, dict), 'Entry documents must be a mapping.')
    documents = {entry.id: retained_document(entry, existing) for entry in parsed.entries}
    require(sum(len(text.encode('utf-8')) for text in documents.values()) <= MAX_MARKDOWN_BYTES,
            'Use at most 10 MiB of entry Markdown per book.')
    return {**content, 'lore_definition': parsed.model_dump(), 'lore_documents': documents}


def entry_sources(version):
    content = decode(version['content']) if isinstance(version['content'], str) else version['content']
    if 'lore_definition' not in content:
        require('lore_documents' not in content, 'Entry documents need their lore definition.')
        return []
    parsed = definition(content)
    documents = content.get('lore_documents', {})
    require(isinstance(documents, dict) and set(documents) == {entry.id for entry in parsed.entries},
            'Entry Markdown documents do not match this book’s entries.')
    result = []
    for entry in parsed.entries:
        text = documents[entry.id]
        require(isinstance(text, str) and parse_entry(text, entry.id) == entry,
                'Entry Markdown does not match its published rule index.')
        result.append({'version_id': version['id'], 'entry_id': entry.id, 'title': entry.title,
                       'markdown': text, 'sha256': source_hash(text)})
    require(sum(len(item['markdown'].encode('utf-8')) for item in result) <= MAX_MARKDOWN_BYTES,
            'Use at most 10 MiB of entry Markdown per book.')
    return result
