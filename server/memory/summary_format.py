"""Recover unambiguous formatting while retaining exact original citation bytes."""
import re

from server.errors import require


def json_payload(output):
    lines = output.strip().splitlines()
    if len(lines) >= 3 and lines[0].strip().lower() in {'```', '```json'} and lines[-1].strip() == '```':
        return '\n'.join(lines[1:-1])
    return output


def source_for(identifier, sources):
    exact = [source for source in sources if source['id'] == identifier]
    if exact:
        return exact[0]
    matches = [source for source in sources if identifier in (source.get('source_id'), source.get('node_id'))]
    require(len(matches) == 1, 'A summary source is unavailable or refers to multiple excerpts. Use its full excerpt ID.', 502)
    return matches[0]


def original_quote(quote, text):
    require(bool(quote.strip()), 'A summary quotation is empty.', 502)
    if quote in text:
        return quote
    expression = r'\s+'.join(re.escape(word) for word in quote.split())
    matches = list(re.finditer(expression, text))
    require(len(matches) == 1, 'A summary quotation has changed words or ambiguous spacing. Choose an exact quotation from its original excerpt.', 502)
    original = matches[0].group()
    require(len(original) <= 600, 'A summary quotation exceeds 600 characters in the original. Choose a shorter quotation.', 502)
    return original


def restore_citations(result, sources):
    items = []
    for item in result.items:
        source = source_for(item.source_id, sources)
        items.append({**item.model_dump(), 'source_id': source['id'],
                      'quotes': [original_quote(quote, source['text']) for quote in item.quotes]})
    return {'items': items}
