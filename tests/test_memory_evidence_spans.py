import hashlib
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from scripts.memory_evidence_spans import (
    EVIDENCE_PROMPT,
    evidence_context,
    parse_evidence,
    ranges,
    render_evidence,
)
from server.database import encode
from server.errors import DomainError
from server.memory.chunks import compile_chunks
from server.memory.prose_sources import source_evidence


def canonical(*texts):
    sources = [source_evidence({'id': f'n{i}', 'role': 'narrator'}, chunk)
               for i, text in enumerate(texts)
               for chunk in compile_chunks(f'message:n{i}', 'Accepted prose', text)]
    return encode({'task': 'Summarize.', 'authority': 'Source prose is authoritative.', 'sources': sources})


def output_for(content, source_index=0):
    source = evidence_context(content)['sources'][source_index]
    return {'items': [{'source_id': source['id'], 'summary': 'A claim remains uncertain.',
                       'evidence_ids': [source['spans'][0]['id']]}]}


@pytest.mark.parametrize('text', [
    '  He said, "Do not leave." \r\nShe paused.\t<wait> & ]]> 日本語 🗝️.  ',
    'a' * 2400,
    '短' * 2400,
    'x. ' * 799,
    ' ' * 1200 + 'No reply.',
    'A sentence without punctuation ' * 70,
    'Line one.\r\n' * 120,
], ids=['exact-unicode', 'long-token', 'non-latin', 'short-sentences', 'whitespace', 'long-sentence', 'crlf'])
def test_segmentation_preserves_all_original_characters_and_bounds(text):
    parts = list(ranges(text))
    assert parts[0][0] == 0 and parts[-1][1] == len(text)
    assert all(0 < end - start <= 600 for start, end in parts)
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))
    assert ''.join(text[start:end] for start, end in parts) == text


def test_render_is_deterministic_and_includes_each_source_character_once():
    content = canonical('  A & B <tag> ]]> \r\nNo promise was fulfilled.  ', 'She heard "maybe."')
    before = str(content)
    rendered = json.loads(render_evidence(content))
    for original, source in zip(json.loads(content)['sources'], rendered['sources'], strict=True):
        assert 'text' not in source
        assert ''.join(s['text'] for s in source['spans']) == original['text']
        assert {k: v for k, v in source.items() if k != 'spans'} == {k: v for k, v in original.items() if k != 'text'}
    assert content == before and render_evidence(content) == render_evidence(content)


def test_exact_quote_resolution_and_optional_whole_fence():
    text = ' "Did she leave?"\r\n"Not yet," he said. A & B <tag> 日本語. '
    content = canonical(text)
    output = json.dumps(output_for(content))
    result = parse_evidence(output, content)
    assert result['items'][0]['quotes'] == [text]
    assert result == parse_evidence('```json\n' + output + '\n```', content)
    assert 'evidence_ids' not in result['items'][0]


@pytest.mark.parametrize('change', ['text', 'identity', 'role', 'offset'])
def test_previous_reference_cannot_resolve_against_changed_source(change):
    content = canonical('Original words, with an unresolved question.')
    output = json.dumps(output_for(content))
    changed = json.loads(content)
    source = changed['sources'][0]
    if change == 'text':
        source['text'] = source['text'].replace('Original', 'Altered!')
        source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    elif change == 'identity':
        source['node_id'] = 'another-node'
    elif change == 'role':
        source['role'] = 'player'
    else:
        source['start'] += 1
        source['end'] += 1
    with pytest.raises(DomainError, match='stale'):
        parse_evidence(output, encode(changed))


def test_cross_source_unknown_and_duplicate_references_fail():
    content = canonical('An uncertain report.', 'A later correction.')
    valid = output_for(content)
    other = evidence_context(content)['sources'][1]['spans'][0]['id']
    for ids in [[other], ['made-up'], valid['items'][0]['evidence_ids'] * 2]:
        altered = deepcopy(valid)
        altered['items'][0]['evidence_ids'] = ids
        with pytest.raises(DomainError):
            parse_evidence(json.dumps(altered), content)


def test_duplicate_source_items_and_blank_evidence_fail():
    content = canonical(' ' * 1200 + 'A late answer.')
    blank = output_for(content)
    with pytest.raises(DomainError, match='Whitespace-only'):
        parse_evidence(json.dumps(blank), content)
    content = canonical('An unresolved answer.')
    duplicated = output_for(content)
    duplicated['items'] *= 2
    with pytest.raises(DomainError, match='repeated'):
        parse_evidence(json.dumps(duplicated), content)


@pytest.mark.parametrize('value', [
    {'items': [{'source_id': 'one', 'summary': 'Claim', 'evidence_ids': []}]},
    {'items': [{'source_id': 'one', 'summary': 'Claim', 'evidence_ids': ['x'] * 5}]},
    {'items': [{'source_id': 'one', 'summary': 'Claim', 'evidence_ids': [1]}]},
    {'items': [{'source_id': 'one', 'summary': 'Claim', 'quotes': ['not supplied']}]},
    {'items': [], 'unknown': True},
], ids=['empty-refs', 'too-many-refs', 'numeric-ref', 'old-quote-contract', 'extra-field'])
def test_output_schema_is_strict_without_cross_contract_fallback(value):
    with pytest.raises(ValidationError):
        parse_evidence(json.dumps(value), canonical('An unresolved answer.'))


def test_all_selected_spans_remain_exact_and_empty_result_is_explicit():
    content = canonical('Very long sentence with no punctuation ' * 50)
    source = evidence_context(content)['sources'][0]
    payload = output_for(content)
    payload['items'][0]['evidence_ids'] = [span['id'] for span in source['spans'][:4]]
    result = parse_evidence(json.dumps(payload), content)
    assert result['items'][0]['quotes'] == [span['text'] for span in source['spans'][:4]]
    assert parse_evidence('{"items":[]}', content) == {'items': []}
    assert '1–4 distinct supplied evidence IDs' in EVIDENCE_PROMPT
    assert 'Do not resolve threads' in EVIDENCE_PROMPT