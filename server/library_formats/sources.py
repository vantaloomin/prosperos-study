"""Versioned Markdown source and its persisted narrative index."""
from hashlib import sha256

from server.database import decode
from server.errors import require
from server.library_formats.markdown import document

MAX_MARKDOWN_BYTES = 10 * 1024 * 1024


def source_hash(markdown):
    return sha256(markdown.encode('utf-8')).hexdigest()


def source_record(version):
    content = decode(version['content']) if isinstance(version['content'], str) else version['content']
    text = content.get('text', '')
    if isinstance(text, str):
        markdown, format_name = text, 'plain-markdown'
    else:
        markdown = document({'kind': 'legacy-lorebook', 'content': content}, '')
        format_name = 'legacy-metadata'
    return {'version_id': version['id'], 'format': format_name,
            'markdown': markdown, 'sha256': source_hash(markdown)}


def validate_source(source, version):
    expected = source_record(version)
    require(source == expected, 'A Markdown source does not match its immutable Library version.')


def validate_new_markdown(content):
    text = content.get('text', '')
    require(isinstance(text, str), 'Lorebook prose must be Markdown text.')
    require(len(text.encode('utf-8')) <= MAX_MARKDOWN_BYTES, 'Use at most 10 MiB of Markdown per book.')
