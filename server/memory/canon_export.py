"""Export selected, published prose only after reviewing loss of native rules."""
import math

from pydantic import Field

from server.database import encode, one
from server.errors import require
from server.library import get_version
from server.library_formats.brain_pack import validate_pack
from server.library_formats.sources import MAX_MARKDOWN_BYTES
from server.lore.documents import definition
from server.memory.canon_compiler import COMPILER, CueIndex, compile_overview
from server.memory.canon_models import canon_policy
from server.memory.chunks import compile_chunks
from server.models import Input


class PackExport(Input):
    include_overview: bool = True
    entry_ids: list[str] = Field(default_factory=list, max_length=500)
    reviewed_rules: bool = False


def export_chunk(chunk, position, cues=None):
    return {'id': f'chunk-{position:05d}-{chunk.digest[:12]}', 'title': chunk.title or 'Canon reference',
            'text': chunk.text, **(cues or {'summary': '', 'topics': [], 'aliases': []}),
            'source': {'file': chunk.source_id, 'doc': chunk.title, 'position': position},
            'tokens': math.ceil(len(chunk.text.encode('utf-8')) / 3)}


def chosen_chunks(version, body):
    result = []
    cues = CueIndex(version['content'])
    if body.include_overview:
        chunks, _ = compile_overview(f"version:{version['id']}", version['name'], version['content'])
        result.extend(export_chunk(chunk, index + 1, cues.fields(chunk))
                      for index, chunk in enumerate(chunks))
    entries = {entry.id: entry for entry in definition(version['content']).entries}
    require(len(body.entry_ids) == len(set(body.entry_ids)), 'Choose each Canon entry once.')
    require(set(body.entry_ids) <= entries.keys(), 'Choose entries from this published version.')
    require(not body.entry_ids or body.reviewed_rules,
            'Review that SGC export turns selected entries into ordinary reference prose without their native activation rules.')
    for key in body.entry_ids:
        entry = entries[key]
        for chunk in compile_chunks(f"entry:{version['id']}:{key}", entry.title, entry.text, 'Canon reference'):
            result.append(export_chunk(chunk, len(result) + 1))
    return result


def export_pack(database, version_id, body):
    with database.connect() as connection:
        version = get_version(connection, version_id)
        kind = one(connection, 'SELECT kind FROM assets WHERE id=?', (version['asset_id'],))['kind']
        require(kind == 'lorebook', 'Choose a published Canon collection.')
    pack = {'schema': 'sgc-brain/1', 'id': f"prospero-{version['id'].replace('-', '').lower()[:48]}",
            'name': version['name'], 'description': f"Canon reference from {version['name']} v{version['number']}.",
            'version': str(version['number']), 'built_at': version['created_at'],
            'source': {'tool': 'prosperos-study', 'schema': COMPILER,
                       'stub': not any(cue.summary or cue.topics or cue.aliases
                                       for cue in canon_policy(version['content']).cues)},
            'chunks': chosen_chunks(version, body)}
    require(bool(pack['chunks']), 'Choose published prose to export. Empty collections have no SGC chunks.')
    try:
        validate_pack(pack)
    except ValueError as error:
        require(False, str(error))
    require(len(encode(pack).encode('utf-8')) <= MAX_MARKDOWN_BYTES,
            'This export exceeds 10 MiB. Choose fewer entries or split the collection.')
    return pack
