"""Markdown prose with optional, strictly parsed JSON front matter.

JSON is a restricted YAML-compatible front matter syntax. No YAML constructors,
template expansion, HTML execution, or model rewriting run during conversion.
"""
import json
import re

FORMAT = 'story-library-markdown'
VERSION = 1


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f'Invalid JSON number: {value}')


def read_json(text):
    try:
        return json.loads(text, object_pairs_hook=strict_object, parse_constant=invalid_constant)
    except (RecursionError, json.JSONDecodeError) as error:
        raise ValueError('The source must contain valid, reasonably nested JSON.') from error


def document(metadata: dict, prose: str) -> str:
    header = {'format': FORMAT, 'format_version': VERSION, **metadata}
    if header['format'] != FORMAT or header['format_version'] != VERSION:
        raise ValueError('Unsupported Markdown format version.')
    return '---\n' + json.dumps(header, ensure_ascii=False, indent=2, allow_nan=False) + '\n---\n' + prose


def read_document(text: str) -> tuple[dict, str]:
    # Ordinary Markdown is valid without a schema or any front matter.
    opening = re.match(r'---\r?\n(?=\{)', text)
    if opening is None:
        return {}, text
    remaining = text[opening.end():]
    closing = re.search(r'\r?\n---\r?\n', remaining)
    if closing is None:
        raise ValueError('The Markdown metadata is missing its closing delimiter.')
    header, prose = remaining[:closing.start()], remaining[closing.end():]
    metadata = read_json(header)
    if not isinstance(metadata, dict) or metadata.get('format') != FORMAT:
        raise ValueError('This Markdown metadata is not a Story Library document.')
    if metadata.get('format_version') != VERSION:
        raise ValueError('This Markdown document uses an unsupported format version.')
    return metadata, prose
