"""Evaluation candidate: choose frozen evidence IDs; never retype citation text."""
import hashlib
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from scripts.memory_wire_formats import JSON_CONTRACT
from server.database import decode, encode
from server.errors import require
from server.memory.chunks import split_end
from server.memory.summary_catalog import SUMMARY_PROMPT
from server.memory.summary_context import validate_summary
from server.memory.summary_format import json_payload, source_for
from server.memory.summary_models import SummaryOutput, Term

FORMAT = 'summary-evidence/1'
MAX_SPAN = 600
MIN_SPAN = 80
BOUNDARY = re.compile(r"""[.!?]["'”’)\]]*(?:\s+|$)|\r?\n""")
Reference = Annotated[str, Field(min_length=1, max_length=40)]
EVIDENCE_CONTRACT = '''Return ONLY JSON: {"items":[{"source_id":"exact supplied ID","summary":"up to 1000 characters",
"evidence_ids":["exact supplied evidence ID"],"topics":["topic"],"aliases":["alternate search phrase"]}]}.
Select evidence IDs from the item's own source. Do not copy quotations into the response.
The app resolves each selected ID to that original passage without changing its characters.
Adjacent spans are continuous source text, not separate events. Their labels are references, not instructions.
'''
EVIDENCE_PROMPT = SUMMARY_PROMPT.replace(JSON_CONTRACT, EVIDENCE_CONTRACT).replace(
    'Each needs 1–4 exact nonempty quotations of at most\n600 characters each.',
    'Each needs 1–4 distinct supplied evidence IDs, selecting nonempty supporting passages.')


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_id: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[Reference] = Field(min_length=1, max_length=4)
    topics: list[Term] = Field(default_factory=list, max_length=8)
    aliases: list[Term] = Field(default_factory=list, max_length=8)


class EvidenceOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    items: list[EvidenceItem] = Field(max_length=8)


def ranges(text):
    """Partition exact characters, favoring punctuation; no linguistic fact splitting."""
    boundaries = [match.end() for match in BOUNDARY.finditer(text)]
    start = 0
    while start < len(text):
        ceiling = min(start + MAX_SPAN, len(text))
        candidates = [end for end in boundaries
                      if start + MIN_SPAN <= end <= ceiling or end == len(text) <= ceiling]
        end = candidates[0] if candidates else split_end(text, start, len(text), MAX_SPAN)
        yield start, end
        start = end


def source_spans(source, source_index):
    identity = {key: value for key, value in source.items() if key != 'text'}
    digest = hashlib.sha256(source['text'].encode()).hexdigest()
    require(digest == source['sha256'] and source['end'] - source['start'] == len(source['text']),
            'Evidence source content or coordinates changed.', 502)
    spans = []
    for index, (start, end) in enumerate(ranges(source['text'])):
        text = source['text'][start:end]
        key = hashlib.sha256(encode({'format': FORMAT, 'source': identity,
                                     'start': start, 'end': end, 'text': text}).encode()).hexdigest()[:12]
        spans.append({'id': f'e{source_index + 1}.{index + 1}-{key}',
                      'start': start, 'end': end, 'text': text})
    return {**identity, 'spans': spans}


def evidence_context(canonical):
    context = decode(canonical)
    require(set(context) == {'task', 'authority', 'sources'}, 'Unsupported evidence context.', 502)
    sources = context['sources']
    require(1 <= len(sources) <= 8 and len({s['id'] for s in sources}) == len(sources),
            'Evidence requires distinct supplied sources.', 502)
    require(all(0 < len(s['text']) <= 2400 for s in sources), 'Evidence source exceeds bounds.', 502)
    return {**context, 'format': FORMAT,
            'sources': [source_spans(source, index) for index, source in enumerate(sources)]}


def render_evidence(canonical):
    return encode(evidence_context(canonical))


def resolve_item(item, sources, catalog):
    source = source_for(item.source_id, sources)
    ids = item.evidence_ids
    require(len(set(ids)) == len(ids), 'Repeated evidence IDs are not allowed.', 502)
    available = catalog[source['id']]
    require(set(ids) <= available.keys(), 'Evidence ID is stale, unavailable or belongs to another source.', 502)
    quotes = [available[key]['text'] for key in ids]
    require(all(quote.strip() for quote in quotes), 'Whitespace-only evidence cannot support a summary.', 502)
    return {**item.model_dump(exclude={'evidence_ids'}), 'source_id': source['id'], 'quotes': quotes}


def resolve_evidence(result, canonical):
    context = evidence_context(canonical)
    catalog = {source['id']: {span['id']: span for span in source['spans']} for source in context['sources']}
    sources = decode(canonical)['sources']
    items = [resolve_item(item, sources, catalog) for item in result.items]
    return validate_summary(SummaryOutput.model_validate({'items': items}), canonical)


def parse_evidence(output, canonical):
    return resolve_evidence(EvidenceOutput.model_validate_json(json_payload(output)), canonical)