"""Pure selection. Only explicit completed-beat calls may produce new draws/state."""
from copy import deepcopy

from server.lore.matching import eligibility, entry_source, keyword_evidence, tokens
from server.lore.models import LoreDefinition
from server.mechanics.randomness import ALGORITHM, Draws


def initial_lore():
    return {'clock': 0, 'entries': []}


def chance_result(entry, prior, clock, draws, stream, enabled, advance):
    if prior.get('active_until', -1) >= clock:
        return True, 'Retained for its sticky duration.', None
    if not enabled or not entry.chance_enabled or entry.kind == 'required':
        return True, 'Matched; no chance draw.', None
    if not advance:
        passed = prior.get('checked_at') == clock and prior.get('passed', False)
        return passed, 'Reusing the saved beat decision.' if prior.get('checked_at') == clock else 'Awaiting a recorded eligible beat; no draw.', prior.get('roll')
    if entry.chance == 0:
        return False, 'Chance is zero; no draw.', None
    roll = draws.die(100, stream, f'Lore flavor: {entry.title}')
    return roll <= entry.chance, 'Chance passed.' if roll <= entry.chance else 'Chance missed.', roll


def record_decision(book, entry, clock, passed, roll, prior):
    record = {**prior, 'asset_id': book['asset_id'], 'version_id': book['version_id'], 'entry_id': entry.id,
              'checked_at': clock, 'passed': passed, 'roll': roll}
    if passed and prior.get('active_until', -1) < clock:
        record.update(active_until=clock + entry.sticky_beats,
                      cooldown_until=clock + entry.sticky_beats + entry.cooldown_beats)
    return record


def entry_decision(book, entry, text, state, rng, draws, advance, remaining):
    key = (book['version_id'], entry.id)
    prior = state['records'].get(key, {})
    source = entry_source(book, entry)
    evidence = keyword_evidence(entry, text)
    estimate = tokens(source)
    reason = eligibility(entry, evidence, state['clock'], prior)
    if not reason and entry.kind == 'flavor' and estimate > remaining:
        reason = 'Optional flavor does not fit this book’s remaining flavor budget; no draw.'
    audit = {'asset_id': book['asset_id'], 'version_id': book['version_id'], 'entry_id': entry.id,
             'title': entry.title, 'kind': entry.kind, 'placement': entry.placement,
             'estimated_tokens': estimate, 'matched': evidence, 'included': False, 'reason': reason, 'roll': None}
    if reason:
        return audit, None
    stream = f"lore:{book['random_stream']}:{entry.id}"
    included, reason, roll = chance_result(entry, prior, state['clock'], draws, stream, rng, advance)
    audit.update(included=included, reason=reason, roll=roll)
    if advance:
        state['records'][key] = record_decision(book, entry, state['clock'], included, roll, prior)
    return audit, source if included else None


def scan_book(book, history, state, rng, draws, advance):
    definition = LoreDefinition.model_validate(book['definition'])
    # Each caller passes only its selected path; trimming occurs independently per book.
    messages = [node for node in history if node['role'] != 'ooc'][-definition.scan_messages:]
    text = '\n'.join(node['text'] for node in messages)
    entries = sorted(definition.entries, key=lambda entry: (entry.kind == 'flavor', -entry.priority, entry.id))
    sources, audits, remaining = [], [], definition.flavor_budget_tokens
    for entry in entries:
        audit, source = entry_decision(book, entry, text, state, rng, draws, advance, remaining)
        audits.append(audit)
        if source:
            sources.append(source)
            if entry.kind == 'flavor':
                remaining -= audit['estimated_tokens']
    return sources, audits, {'asset_id': book['asset_id'], 'version_id': book['version_id'],
        'flavor_budget_tokens': definition.flavor_budget_tokens, 'flavor_used_tokens': definition.flavor_budget_tokens - remaining,
        'required_tokens': sum(item['estimated_tokens'] for item in audits if item['included'] and item['kind'] == 'required'),
        'scanned_messages': len(messages)}


def select_lore(books, history, before=None, rng=False, advance=False, seed='not-drawn'):
    before = deepcopy(before or initial_lore())
    state = {'clock': before['clock'] + int(advance),
             'records': {(item['version_id'], item['entry_id']): item for item in before['entries']}}
    sources, audits, budgets, draws = [], [], [], Draws(seed)
    for book in sorted(books, key=lambda value: (-value.get('priority', 0), value.get('source_version_id', value['version_id']))):
        selected, results, budget = scan_book(book, history, state, rng, draws, advance)
        sources.extend(selected)
        audits.extend(results)
        budgets.append(budget)
    positions = {'header': 0, 'recent': 1, 'tail': 2}
    sources.sort(key=lambda item: positions[item['placement']])
    after = {'clock': state['clock'], 'entries': list(state['records'].values())} if advance else before
    return {'sources': sources, 'entries': audits, 'budgets': budgets, 'before': before, 'after': after,
            'algorithm': ALGORITHM, 'seed': seed, 'draws': draws.log, 'advanced': advance, 'rng_enabled': rng}
