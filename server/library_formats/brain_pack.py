"""Independently implemented sgc-brain/1 format reader, converted for review.

Contract references and pinned revisions are recorded in planning. Source paths
and unknown fields are preserved as data; they are never opened or executed.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from server.library_formats.markdown import document
from server.library_formats.sources import MAX_MARKDOWN_BYTES
from server.memory.canon_compiler import source_digest

Term = Annotated[str, Field(max_length=2000)]


class PackChunk(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    id: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=8000)
    text: str = Field(min_length=1, max_length=8000)
    summary: str = Field(max_length=32000)
    topics: list[Term] = Field(max_length=256)
    aliases: list[Term] = Field(max_length=256)
    source: dict = Field(default_factory=dict)
    tokens: float = Field(allow_inf_nan=False)

    @model_validator(mode='after')
    def compatible_characters(self):
        if len(self.text.encode('utf-16-le')) // 2 > 8000:
            raise ValueError('Chunk text exceeds the SGC limit of 8,000 UTF-16 characters.')
        return self


class PackSource(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    tool: str = ''
    schema_name: str = Field(default='', alias='schema')
    stub: bool


class BrainPack(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    schema_name: Literal['sgc-brain/1'] = Field(alias='schema')
    id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    name: str = Field(max_length=8000)
    description: str = Field(max_length=100000)
    version: str = Field(max_length=2000)
    built_at: str = Field(max_length=2000)
    source: PackSource
    chunks: list[PackChunk] = Field(min_length=1, max_length=5000)

    @model_validator(mode='after')
    def unique_chunks(self):
        if len({chunk.id for chunk in self.chunks}) != len(self.chunks):
            raise ValueError('Chunk IDs must be unique within the pack.')
        return self


def validate_pack(value):
    try:
        return BrainPack.model_validate(value)
    except ValidationError as error:
        issue = error.errors()[0]
        location = '.'.join(map(str, issue['loc'])) or 'pack'
        raise ValueError(f"SGC pack {location}: {issue['msg']}") from error


def pack_markdown(pack, original):
    sections, cues, files, offset = [], [], {}, 0
    for index, chunk in enumerate(pack.chunks):
        section = f'## {chunk.title}\n\n{chunk.text}\n\n'
        sections.append(section)
        cues.append({'start': offset, 'end': offset + len(section), 'sha256': source_digest(section),
                     'summary': chunk.summary, 'topics': chunk.topics, 'aliases': chunk.aliases})
        offset += len(section)
        files[f'canon/chunks/{index + 1:05d}.md'] = document(
            {'kind': 'sgc-reference', 'source_index': index,
             'source_fields': {key: value for key, value in original['chunks'][index].items() if key != 'text'}},
            chunk.text)
    text = ''.join(sections)
    if len(text.encode('utf-8')) > MAX_MARKDOWN_BYTES:
        raise ValueError('The converted Canon overview exceeds 10 MiB. Split the source pack before importing.')
    files['canon/book.md'] = document({'kind': 'lorebook', 'source_fields': {
        key: value for key, value in original.items() if key != 'chunks'}}, text)
    return text, cues, files


def convert_pack(value, source):
    pack = validate_pack(value)
    text, cues, files = pack_markdown(pack, value)
    issues = [
        {'path': 'chunks', 'message': f'All {len(pack.chunks)} chunk texts become editable Markdown below. '
         'Review the prose before publication; nothing attaches to a Story automatically.'},
        {'path': 'search', 'message': 'Summaries, topics and aliases are search cues, not facts sent to the writer. '
         'A cue stops working if its exact source span changes. The original pack and metadata stay preserved.'},
        {'path': 'rules', 'message': 'This pack supplies reference prose, not character knowledge, events or native '
         'activation rules. Source paths and unknown metadata are never executed or fetched.'},
    ]
    return {'converter_version': 1, 'format': 'sgc-brain', 'card_version': None,
            'source_sha256': source_digest(source.decode('utf-8')),
            'files': files, 'issues': issues, 'status': 'converted-for-review', 'published': False,
            'drafts': [{'part': 'lorebook', 'kind': 'lorebook', 'name': pack.name[:120].strip() or 'Imported Canon',
                        'content': {'text': text, 'canon_recall': {'mode': 'relevant', 'cues': cues}}}]}
