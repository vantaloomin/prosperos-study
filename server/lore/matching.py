import math
import re

from server.database import encode


def tokens(value):
    """Same documented UTF-8 estimate as full request assembly; not a tokenizer."""
    return math.ceil(len(encode(value).encode('utf-8')) / 3)


def matches(term, text, entry):
    if not entry.case_sensitive:
        term, text = term.casefold(), text.casefold()
    if not entry.whole_words:
        return term in text
    # Literal matching only: imported keyword strings cannot execute regex syntax.
    return re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text) is not None


def keyword_evidence(entry, text):
    return {'primary': [term for term in entry.keywords if matches(term, text, entry)],
            'secondary': [term for term in entry.secondary if matches(term, text, entry)]}


def exclusion(entry, evidence):
    if entry.secondary_mode == 'exclude' and evidence['secondary']:
        return 'An excluded keyword is present.'
    if entry.secondary_mode == 'require' and not evidence['secondary']:
        return 'No required secondary keyword matched.'
    return None


def primary_match(entry, evidence):
    if entry.activation == 'always':
        return True
    return len(evidence['primary']) == len(entry.keywords) if entry.match == 'all' else bool(evidence['primary'])


def eligibility(entry, evidence, clock, prior):
    if not entry.enabled:
        return 'This entry is off.'
    if not entry.text.strip():
        return 'This entry has no prose.'
    if clock < entry.minimum_beats:
        return f'Available after {entry.minimum_beats} completed beats; currently {clock}.'
    blocked = exclusion(entry, evidence)
    if blocked:
        return blocked
    if prior.get('active_until', -1) >= clock:
        return None
    if prior.get('cooldown_until', -1) >= clock:
        return 'The entry is resting after its last activation.'
    if not primary_match(entry, evidence):
        return 'No matching primary keyword condition.'
    return None


def entry_source(book, entry):
    return {'id': f"lore:{book.get('source_version_id', book['version_id'])}:{entry.id}", 'kind': 'world reference',
            'title': f"{book['name']} · {entry.title}", 'text': entry.text, 'placement': entry.placement,
            'knowledge': 'World reference does not establish what any character knows or what has happened.'}
