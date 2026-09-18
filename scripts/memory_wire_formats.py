"""Frozen evaluation contracts; not production prompt defaults or automatic repairs."""
import json

from pydantic import ValidationError

from scripts.memory_wire_xml import parse_summary_xml, parse_tree, render_context
from server.database import decode
from server.errors import DomainError
from server.memory.summary_catalog import SUMMARY_PROMPT
from server.memory.summary_context import validate_summary
from server.memory.summary_format import json_payload, restore_citations
from server.memory.summary_models import SummaryOutput

JSON_CONTRACT = SUMMARY_PROMPT[SUMMARY_PROMPT.index('Return ONLY JSON:'):SUMMARY_PROMPT.index('Return at most one')]
XML_CONTRACT = '''Return ONLY XML: <scribe task="summary"><items><item source="exact supplied ID">
<summary>up to 1000 characters</summary><quotes><quote>short exact supporting quotation</quote></quotes>
<topics><topic>topic</topic></topics><aliases><alias>alternate search phrase</alias></aliases>
</item></items></scribe>.
Use escaped text or valid CDATA for prose. No declaration, DOCTYPE, entity declarations, namespaces, processing
instructions or comments. Escape literal ampersands and angle brackets. Do not add unknown or repeated
fields. Empty items, topics and aliases use empty containers. Keep source identifiers in source attributes.
'''
CONDITIONS = (('json', 'json'), ('json', 'xml'), ('xml', 'xml'), ('xml', 'json'))


def instructions(output_format):
    if output_format == 'json':
        return SUMMARY_PROMPT
    if output_format == 'xml':
        return SUMMARY_PROMPT.replace(JSON_CONTRACT, XML_CONTRACT)
    raise ValueError('Unsupported summary output format')


def content_for(canonical, input_format):
    if input_format == 'json':
        return canonical
    if input_format == 'xml':
        return render_context(decode(canonical))
    raise ValueError('Unsupported summary input format')


def syntax_value(output, output_format):
    if output_format == 'json':
        return json.loads(json_payload(output))
    if output_format == 'xml':
        return parse_tree(output)
    raise ValueError('Unsupported summary output format')


def assess_output(output, output_format, canonical):
    report = {'syntax': False, 'schema': False, 'sources': False, 'quotes': False,
              'result': None, 'error': '', 'format_recovered': False}
    try:
        value = syntax_value(output, output_format)
        report['syntax'] = True
        if output_format == 'xml':
            value = parse_summary_xml(output)
        model = SummaryOutput.model_validate(value)
        report['schema'] = True
        sources = decode(canonical)['sources']
        from server.memory.summary_format import source_for
        ids = [source_for(item.source_id, sources)['id'] for item in model.items]
        if len(ids) != len(set(ids)):
            raise DomainError('Repeated canonical source IDs.')
        report['sources'] = True
        restored = SummaryOutput.model_validate(restore_citations(model, sources))
        report['result'] = validate_summary(restored, canonical)
        report['quotes'] = True
        report['format_recovered'] = report['result'] != value or output.strip().startswith('```')
    except (DomainError, ValidationError, json.JSONDecodeError) as error:
        report['error'] = str(error)
    return report
