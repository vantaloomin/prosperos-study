"""Local author preparation: exact evidence and recorded knowledge, never new facts."""
from collections import defaultdict

from pydantic import Field, model_validator

from server.database import one
from server.errors import require
from server.memory.chunks import Chunk, compile_chunks
from server.memory.control_sources import available_sources, characters, pinned_items
from server.memory.control_state import control_view
from server.memory.index import connection_index
from server.memory.knowledge import matches_character, permitted_entries
from server.memory.retrieval import Corpus
from server.models import Input
from server.stories import check_revision


class RehearsalRequest(Input):
    expected_revision: int = Field(ge=0)
    expected_version_id: str | None = None
    query: str = Field(min_length=1, max_length=1000)
    views: list[str] = Field(default_factory=list, max_length=8)
    include_library: bool = False
    limit: int = Field(default=8, ge=1, le=12)

    @model_validator(mode='after')
    def valid_query(self):
        if not self.query.strip() or len(self.views) != len(set(self.views)):
            raise ValueError('Enter a search topic and choose each viewpoint once.')
        return self


def viewpoints(connection, branch, controls):
    items = characters(pinned_items(connection, branch))
    result = {('character:' + item['id']): {'key': 'character:' + item['id'], 'subject': item['name'],
              'character_id': item['id']} for item in items}
    for entry in controls['entries']:
        if entry['kind'] == 'knowledge' and entry['enabled'] and not entry.get('character_id'):
            key = 'name:' + entry['subject'].casefold()
            result.setdefault(key, {'key': key, 'subject': entry['subject'], 'character_id': None})
    return list(result.values())


def boundary(branch, controls):
    return {'branch_id': branch['id'], 'head_id': branch['head_id'], 'revision': branch['revision'],
            'manifest_id': branch['manifest_id'], 'version_id': controls['version_id']}


def catalogue(connection, branch):
    controls = control_view(connection, branch)
    return {'boundary': boundary(branch, controls), 'views': viewpoints(connection, branch, controls)}


def search_sources(sources, entries, query, limit):
    cues = defaultdict(list)
    for entry in entries:
        if entry['kind'] in {'knowledge', 'conflict'}:
            for source in entry['sources']:
                cues[source['id']].append(entry['subject'] + ' ' + entry['text'])
    chunks = [Chunk(source['id'], source['source_id'], source['title'], source['text'],
                    source['start'], source['end'], source['sha256'], source['kind'], tuple(cues[source['id']])) for source in sources]
    hits = Corpus(chunks).search(query, limit=limit + 1)
    indexed = {source['id']: source for source in sources}
    return [{'source': indexed[hit.chunk.id], 'matched': hit.matched} for hit in hits[:limit]], len(hits) > limit


def knowledge_index(controls, view):
    permitted = permitted_entries(controls, view['subject'], view['character_id'])
    granted = defaultdict(list)
    denied = defaultdict(list)
    for entry in permitted:
        for source in entry['sources']:
            granted[source['id']].append(entry)
    for entry in [*controls['entries'], *controls.get('unavailable_entries', [])]:
        if (entry['enabled'] and entry['kind'] == 'knowledge' and entry['stance'] == 'unaware'
                and matches_character(entry, view['subject'], view['character_id'])):
            for source in entry['sources']:
                denied[source['id']].append(entry['id'])
    return {'view': view, 'granted': granted, 'denied': denied}


def knowledge_cell(index, source_id):
    denied = index['denied'].get(source_id, [])
    grants = index['granted'].get(source_id, [])
    states = ['unaware'] if denied else sorted({entry['stance'] for entry in grants}) or ['unrecorded']
    return {'view': index['view']['key'], 'states': states,
            'decision_ids': denied or [entry['id'] for entry in grants]}


def evidence_rows(hits, indexes):
    result = []
    for hit in hits:
        cells = [knowledge_cell(index, hit['source']['id']) for index in indexes]
        signatures = {tuple(cell['states']) for cell in cells}
        result.append({**hit, 'knowledge': cells, 'different_states': len(signatures) > 1})
    return result


def matching_conflicts(entries, query):
    conflicts = [entry for entry in entries if entry['kind'] == 'conflict']
    chunks = [chunk for entry in conflicts for chunk in compile_chunks(entry['id'], entry['subject'],
              entry['text'] + '\n' + '\n'.join(source['text'] for source in entry['sources']))]
    hits = Corpus(chunks).search(query, limit=len(chunks))
    ids = list(dict.fromkeys(hit.chunk.source_id for hit in hits))
    by_id = {entry['id']: entry for entry in conflicts}
    return [by_id[key] for key in ids[:6]], len(ids) > 6


def decision_details(entries, rows):
    ids = {key for row in rows for cell in row['knowledge'] for key in cell['decision_ids']}
    # Only current, complete decisions may expose interpretations or all their citations.
    # A stale mixed denial still blocks matching evidence, but never reveals its retired text here.
    return [entry for entry in entries if entry['id'] in ids]


def rehearse(connection, branch, body):
    check_revision(branch, body.expected_revision)
    controls = control_view(connection, branch)
    require(controls['version_id'] == body.expected_version_id, 'Author decisions changed. Refresh the rehearsal before searching.', 409)
    choices = {item['key']: item for item in viewpoints(connection, branch, controls)}
    require(set(body.views) <= choices.keys(), 'A selected viewpoint is unavailable on this path. Review the viewpoint selection.', 409)
    selected = [choices[key] for key in body.views]
    entries = [entry for entry in controls['entries'] if entry['enabled']]
    indexes = [knowledge_index(controls, view) for view in selected]
    with connection_index(connection):
        sources = available_sources(connection, branch, body.include_library)
        hits, more = search_sources(sources, entries, body.query, body.limit)
        conflicts, more_conflicts = matching_conflicts(entries, body.query)
    rows = evidence_rows(hits, indexes)
    return {'algorithm': 'prospero-rehearsal-v1', 'boundary': boundary(branch, controls), 'query': body.query,
            'include_library': body.include_library, 'views': selected, 'source_count': len(sources),
            'items': rows, 'more_matches': more, 'conflicts': conflicts, 'more_conflicts': more_conflicts,
            'decisions': decision_details(entries, rows), 'unavailable_decisions': len(controls.get('unavailable_entries', []))}


class Rehearsals:
    def __init__(self, database):
        self.database = database

    def views(self, branch_id):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            return catalogue(connection, branch)

    def search(self, branch_id, body):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            return rehearse(connection, branch, body)
