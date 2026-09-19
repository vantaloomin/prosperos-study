"""Content signatures for independently implemented external JSON readers.

Format facts and research references live in planning/import-compatibility.md.
These signatures select a reader; they never execute imported content.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class JsonFormat:
    id: str
    label: str
    kind: str
    matches: Callable


def portable_book(value):
    entries = value.get('entries')
    return isinstance(entries, list) and bool(entries) and all(
        isinstance(entry, dict) and 'content' in entry and 'keys' in entry for entry in entries)


FORMATS = (
    JsonFormat('pygmalion', 'Pygmalion character', 'character',
               lambda value: 'char_name' in value and 'char_persona' in value),
    JsonFormat('backyard-legacy', 'Backyard / Faraday legacy character', 'character',
               lambda value: 'aiName' in value and 'aiPersona' in value),
    JsonFormat('novelai-lorebook', 'NovelAI lorebook', 'lorebook',
               lambda value: 'lorebookVersion' in value),
    JsonFormat('agnai-lorebook', 'Agnai memory book', 'lorebook',
               lambda value: value.get('kind') == 'memory'),
    JsonFormat('risu-lorebook', 'RisuAI lorebook', 'lorebook',
               lambda value: value.get('type') == 'risu'),
    JsonFormat('sillytavern-lorebook', 'SillyTavern world info', 'lorebook',
               lambda value: isinstance(value.get('entries'), dict)),
    JsonFormat('character-book', 'Portable character lorebook', 'lorebook', portable_book),
)


def external_format(value):
    if not isinstance(value, dict):
        return None
    matches = [adapter for adapter in FORMATS if adapter.matches(value)]
    # Explicit native envelopes take precedence over the portable entry shape.
    if len(matches) > 1:
        matches = [adapter for adapter in matches if adapter.id != 'character-book']
    if len(matches) > 1:
        names = ', '.join(adapter.label for adapter in matches)
        raise ValueError(f'This JSON matches conflicting formats ({names}). Export a single named format before importing.')
    return matches[0] if matches else None


def text_field(value, key, default=''):
    result = value.get(key, default)
    if not isinstance(result, str):
        raise ValueError(f'Imported {key} must be text.')
    return result
