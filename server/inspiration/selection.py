"""Exact integer-weight sampling; previews use a separate, reproducible stream."""
from hashlib import sha256

from server.database import encode
from server.errors import require
from server.inspiration.models import weight_units


def eligibility(content, filters):
    ids = {card['id'] for card in content['cards']}
    require(set(filters['excluded_ids']) <= ids, 'An excluded card is missing from this deck version. Review your exclusions.')
    rows = []
    for card in content['cards']:
        reason = exclusion_reason(card, filters)
        rows.append({'card_id': card['id'], 'reason': reason, 'units': 0 if reason else weight_units(card['weight'])})
    total = sum(row['units'] for row in rows)
    require(total > 0, 'No cards are eligible. Enable a card or relax the tags and exclusions.')
    return {'protocol': 1, 'replacement': True, 'filters': filters, 'total_units': total,
            'cards': [{**row, 'probability': {'numerator': row['units'], 'denominator': total}} for row in rows]}


def exclusion_reason(card, filters):
    if not card['enabled']:
        return 'disabled'
    if card['id'] in filters['excluded_ids']:
        return 'excluded'
    if not set(filters['tags']) <= set(card['tags']):
        return 'missing-required-tag'
    return ''


def selected_card(selection, ticket):
    require(type(ticket) is int and 0 <= ticket < selection['total_units'], 'Invalid recorded draw ticket.')
    for row in selection['cards']:
        if ticket < row['units']:
            return row['card_id']
        ticket -= row['units']
    raise ValueError('Invalid eligible population.')


def preview_ticket(seed, index, total):
    # Rejection sampling avoids modulo bias and does not touch global random state.
    ceiling, attempt = (2 ** 256 // total) * total, 0
    while True:
        value = int.from_bytes(sha256(encode(['inspiration-preview-1', seed, index, attempt]).encode()).digest(), 'big')
        if value < ceiling:
            return value % total
        attempt += 1


def preview(body):
    content, filters = body.content.model_dump(), body.filters.model_dump()
    selection = eligibility(content, filters)
    cards = {card['id']: card for card in content['cards']}
    results = []
    for index in range(body.count):
        ticket = preview_ticket(body.seed, index, selection['total_units'])
        results.append({'ticket': ticket, 'card': cards[selected_card(selection, ticket)]})
    return {'selection': selection, 'results': results, 'seed': body.seed, 'recorded': False}
