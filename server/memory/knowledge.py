"""Explicit character evidence grants, filtered before any local search or prompt."""
import hashlib

from server.database import encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.knowledge_evidence import source_link
from server.memory.retrieval import Corpus
from server.providers.capabilities import input_capacity

GUIDANCE = (
    'Write from this character evidence view. Only the explicitly granted excerpts and '
    'interpretations below are available to this character. Beliefs may be false and '
    'uncertain accounts remain uncertain. Missing material is unknown, not proof of absence. '
    'Do not invent an unseen event or revelation to fill a gap. Grants describe knowledge, '
    'not new story events. This request contains no automatic Canon, private background, '
    'other character notes, or prepared chance. The author direction is explicit guidance.'
)


def matches_character(entry, subject, character_id):
    if character_id:
        return entry.get('character_id') == character_id
    return not entry.get('character_id') and entry['subject'].casefold() == (subject or '').casefold()


def permitted_entries(controls, subject, character_id=None):
    matches = [entry for entry in controls['entries'] if entry['enabled'] and entry['kind'] == 'knowledge'
               and matches_character(entry, subject, character_id)]
    # An edition change may retire part of a denial. It must never widen grants
    # to its remaining exact prose/reference spans without an author decision.
    denials = [entry for entry in [*matches, *controls.get('unavailable_entries', [])]
               if entry['enabled'] and entry['kind'] == 'knowledge' and entry['stance'] == 'unaware'
               and matches_character(entry, subject, character_id)]
    denied = {source['id'] for entry in denials for source in entry['sources']}
    # Suppress a whole interpretation if any of its supporting sources is denied.
    # Retaining its text with a partially removed citation could reveal the denied fact.
    return [entry for entry in matches if entry['stance'] != 'unaware'
            and not any(source['id'] in denied for source in entry['sources'])]


def safe_preferences(settings):
    allowed = {'experience': ('directed', 'scene', 'roleplay'), 'player_agency': ('shared', 'user')}
    return {key: settings[key] if settings.get(key) in choices else choices[-1] for key, choices in allowed.items()}


REFERENCE_GUIDANCE = GUIDANCE + (
    ' Explicit Canon or Character excerpts below are edition-bound reference grants, not '
    'accepted events. No other fields, conditional entries, greetings or author notes are granted.'
)


def packet(subject, direction, entries, writing=None, character_id=None, references=False, guidance=None):
    view = {'subject': subject, 'rule': REFERENCE_GUIDANCE if references else GUIDANCE}
    if character_id:
        view['character_id'] = character_id
    return {'story': {'settings': safe_preferences(writing or {})}, 'knowledge_view': view, 'knowledge': entries,
            'direction': direction, **({'writing_guidance': guidance} if guidance else {})}


def ranked_entries(entries, direction):
    # No broader history, summary aliases, world facts or denied text enters this corpus.
    chunks = [chunk for entry in entries for chunk in compile_chunks(entry['id'], entry['subject'],
              entry['text'] + '\n' + '\n'.join(source['text'] for source in entry['sources']))]
    hits = Corpus(chunks).search(direction, limit=64)
    by_id = {entry['id']: entry for entry in entries}
    ids = list(dict.fromkeys([hit.chunk.source_id for hit in hits] + [entry['id'] for entry in reversed(entries)]))
    return [by_id[key] for key in ids]


def select_entries(entries, subject, direction, prompt, target, writing, character_id=None, references=False):
    if token_estimate(prompt, packet(subject, direction, entries, writing, character_id, references)) <= target:
        return entries
    selected = []
    for entry in ranked_entries(entries, direction):
        trial = [*selected, entry]
        if token_estimate(prompt, packet(subject, direction, trial, writing, character_id, references)) <= target:
            selected = trial
    require(selected, 'No complete character evidence decision fits this model allowance. Shorten its instructions, '
            'select fewer excerpts per decision, or choose a larger context. Original sources are preserved.', 409)
    chosen = {entry['id'] for entry in selected}
    return [entry for entry in entries if entry['id'] in chosen]


def prepare_knowledge(controls, subject, direction, prompt, profiles, writing=None, character_id=None, guidance=None):
    entries = permitted_entries(controls, subject, character_id)
    require(entries, 'This character has no enabled, permitted evidence. Add known, believed or uncertain '
            'excerpts in Story memory > Author decisions. A does-not-know decision overrides the same excerpt.', 409)
    subject = subject or entries[0]['subject']
    references = bool(character_id) or any('version_id' in source for entry in entries for source in entry['sources'])
    allowance = min(input_capacity(profile['config']) for profile in profiles)
    margin = min(512, max(128, allowance // 50))
    selected = select_entries(entries, subject, direction, prompt, allowance - margin, writing, character_id, references)
    context = packet(subject, direction, selected, writing, character_id, references, guidance)
    # Styling must not displace any evidence the ordinary character view kept.
    require(token_estimate(prompt, context) <= allowance - margin,
            'Writing guidance does not fit alongside the selected character evidence. '
            'Choose less guidance or a larger model allowance. No evidence was dropped to fit the style.', 409)
    content = encode(context)
    sources = {source['id']: source for entry in selected for source in entry['sources']}
    links = [source_link(source) for source in sources.values()]
    report = {'algorithm': 'prospero-character-evidence-v1', 'subject': subject,
              'permitted_decisions': len(entries), 'selected_decisions': len(selected),
              'selected_ids': [entry['id'] for entry in selected], 'source_count': len(sources),
              'input_allowance': allowance, 'overhead_margin': margin,
              'content_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}
    if references:
        report['algorithm'] = 'prospero-character-evidence-v2'
    if guidance:
        report.update(algorithm='prospero-character-evidence-v3', reference_grants=references)
    if character_id:
        report['character_id'] = character_id
    return content, report, links
