import json
from copy import deepcopy
from xml.etree.ElementTree import fromstring

import pytest

from scripts.memory_wire_formats import assess_output, content_for, instructions
from scripts.memory_wire_xml import escaped, parse_summary_xml, render_context
from server.database import encode
from server.errors import DomainError
from server.memory.chunks import compile_chunks
from server.memory.prose_sources import source_evidence
from server.memory.summary_catalog import SUMMARY_PROMPT


def context(text='Elin did not\nopen the gate.', node_id='one'):
    node = {'id': node_id, 'role': 'narrator'}
    sources = [source_evidence(node, chunk) for chunk in compile_chunks('message:' + node_id, 'Scene & "label"', text)]
    return {'task': 'Summarize.', 'authority': 'Derived, not fact.', 'sources': sources}


def valid_xml(source='one', quote='did not open the gate.'):
    return f'<scribe task="summary"><items><item source="{source}"><summary>A delay.</summary><quotes><quote>{quote}</quote></quotes><topics/><aliases/></item></items></scribe>'


def test_input_rendering_preserves_every_value_and_prose_character():
    original = context('  A & B <tag> "quote"\r\nline\twith ]]> and \U0001f511.  ', 'one & "name"')
    before = deepcopy(original)
    rendered = render_context(original)
    root = fromstring(rendered)
    assert root.findtext('task') == original['task'] and root.findtext('authority') == original['authority']
    for element, source in zip(root.find('sources'), original['sources'], strict=True):
        recovered = {**element.attrib, 'title': element.findtext('title'), 'text': element.findtext('text')}
        for key in ['start', 'end']:
            recovered[key] = int(recovered[key])
        assert recovered == source
    assert original == before and render_context(original) == rendered
    assert '&lt;tag&gt;' in rendered and '&#13;' in rendered


@pytest.mark.parametrize('text', ['\0', '\x01', '\ud800', '\ufffe'])
def test_unrepresentable_input_is_rejected_without_replacement(text):
    with pytest.raises(DomainError, match='cannot represent'):
        escaped(text)


def test_input_unknown_shape_is_not_silently_discarded():
    value = context()
    value['sources'][0]['new_private_field'] = 'keep me'
    with pytest.raises(DomainError, match='source shape'):
        render_context(value)
    with pytest.raises(DomainError, match='context shape'):
        render_context({**context(), 'other': []})


@pytest.mark.parametrize('payload', [
    '<!DOCTYPE scribe [<!ENTITY x "expanded">]>' + valid_xml(quote='&x;'),
    '<!DOCTYPE scribe SYSTEM "file:///no-read">' + valid_xml(),
    '<?xml version="1.0"?>' + valid_xml(),
    '<?go something?>' + valid_xml(),
    '<!--comment-->' + valid_xml(),
    valid_xml().replace('<items>', '<items xmlns="urn:test">'),
    valid_xml().replace('<items>', '<items xmlns:unused="urn:test">'),
    valid_xml() + valid_xml(),
    'A preamble. ' + valid_xml(),
    valid_xml() + ' Extra prose.',
    '<a>' * 13 + '</a>' * 13,
    '<a>' + '<b/>' * 513 + '</a>',
    'x' * 262145,
    valid_xml(quote='broken & literal'),
    valid_xml(quote='<![CDATA[broken ]]> extra ]]>'),
], ids=['entity', 'external-dtd', 'declaration', 'pi', 'comment', 'namespace', 'unused-namespace', 'two-roots', 'preamble', 'trailer', 'depth', 'node-count', 'byte-count', 'raw-ampersand', 'broken-cdata'])
def test_untrusted_invalid_or_oversized_xml_is_rejected(payload):
    with pytest.raises(DomainError):
        parse_summary_xml(payload)


@pytest.mark.parametrize('change', [
    lambda x: x.replace('<summary>A delay.</summary>', '<summary>A delay.</summary><summary>Another.</summary>'),
    lambda x: x.replace('<topics/>', '<extra/>'),
    lambda x: x.replace('<item source="one">', '<item source="one" source_id="other">'),
    lambda x: x.replace('<summary>A delay.</summary>', '<summary><bold>A delay.</bold></summary>'),
    lambda x: x.replace('<items>', '<items>hidden prose'),
    lambda x: x.replace('<quotes><quote>', '<quotes extra="yes"><quote>'),
    lambda x: x.replace('task="summary"', 'task="continuity"'),
])
def test_shape_violations_are_not_repaired(change):
    report = assess_output(change(valid_xml()), 'xml', encode(context()))
    assert report['syntax'] and not report['schema'] and report['error']


def test_cdata_and_escaped_prose_have_identical_typed_results():
    escaped_xml = valid_xml(quote='A &amp; B &lt;C&gt; ] ]&gt;')
    cdata_xml = valid_xml(quote='<![CDATA[A & B <C> ] ]>]]>')
    assert parse_summary_xml(escaped_xml) == parse_summary_xml(cdata_xml)


def test_valid_xml_uses_the_same_source_and_quote_guards_as_json():
    canonical = encode(context())
    xml = '```xml\n' + valid_xml() + '\n```'
    value = parse_summary_xml(xml)
    a, b = assess_output(xml, 'xml', canonical), assess_output(json.dumps(value), 'json', canonical)
    assert a['result'] == b['result'] and a['quotes'] and a['format_recovered']
    assert a['result']['items'][0]['quotes'] == ['did not\nopen the gate.']
    changed = assess_output(valid_xml(quote='did open the gate.'), 'xml', canonical)
    assert changed['schema'] and changed['sources'] and not changed['quotes']
    foreign = assess_output(valid_xml(source='other'), 'xml', canonical)
    assert foreign['schema'] and not foreign['sources']


def test_missing_items_and_empty_items_are_distinct_and_no_cross_format_fallback():
    canonical = encode(context())
    assert assess_output('<scribe task="summary"><items/></scribe>', 'xml', canonical)['result'] == {'items': []}
    assert not assess_output('<scribe task="summary"/>', 'xml', canonical)['schema']
    assert not assess_output('{"items":[]}', 'xml', canonical)['syntax']
    assert not assess_output(valid_xml(), 'json', canonical)['syntax']


def test_json_control_keeps_production_prompt_and_frozen_content_bytes():
    canonical = json.dumps(context(), indent=2, ensure_ascii=True)
    assert content_for(canonical, 'json') == canonical
    assert instructions('json') == SUMMARY_PROMPT
    assert 'Do not resolve threads' in instructions('xml') and 'Return ONLY XML' in instructions('xml')
