"""Evaluation-only summary XML dialect. No application runner imports this module."""
import re
from xml.etree.ElementTree import ParseError, TreeBuilder
from xml.sax.saxutils import escape

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import DefusedXMLParser

from server.errors import DomainError, require

FORMAT = 'summary-xml/1'
MAX_BYTES = 262144
SOURCE_ATTRIBUTES = ('id', 'source_id', 'node_id', 'role', 'start', 'end', 'sha256', 'kind')
INVALID_CHAR = re.compile(r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')


def escaped(value, attribute=False):
    text = str(value)
    require(not INVALID_CHAR.search(text), 'This source contains characters XML 1.0 cannot represent.')
    result = escape(text, {'"': '&quot;'}).replace('\r', '&#13;')
    return result.replace('\n', '&#10;').replace('\t', '&#9;') if attribute else result


def source_element(source):
    require(set(source) == set(SOURCE_ATTRIBUTES) | {'title', 'text'}, 'Unsupported source shape for summary XML.')
    attributes = ' '.join(f'{key}="{escaped(source[key], True)}"' for key in SOURCE_ATTRIBUTES)
    return f'<source {attributes}><title>{escaped(source["title"])}</title><text>{escaped(source["text"])}</text></source>'


def render_context(context):
    require(set(context) == {'task', 'authority', 'sources'}, 'Unsupported context shape for summary XML.')
    sources = '\n'.join(source_element(source) for source in context['sources'])
    return (f'<context>\n<task>{escaped(context["task"])}</task>\n'
            f'<authority>{escaped(context["authority"])}</authority>\n<sources>\n{sources}\n</sources>\n</context>')


def unfence(text):
    lines = text.strip().splitlines()
    if len(lines) >= 3 and lines[0].strip().lower() in {'```', '```xml'} and lines[-1].strip() == '```':
        return '\n'.join(lines[1:-1])
    return text


class BoundedTree(TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = self.nodes = self.characters = 0

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        require(self.depth <= 12 and self.nodes <= 512, 'XML response exceeds structural limits.', 502)
        require('{' not in tag and all('{' not in key for key in attrs), 'XML namespaces are not supported.', 502)
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)

    def data(self, text):
        self.characters += len(text)
        require(self.characters <= MAX_BYTES, 'XML response exceeds text limits.', 502)
        return super().data(text)

    def comment(self, text):
        raise DomainError('XML comments are not part of this response contract.', 502)

    def pi(self, target, text):
        raise DomainError('XML processing instructions are not allowed.', 502)

    def start_ns(self, prefix, uri):
        raise DomainError('XML namespaces are not supported.', 502)


def parse_tree(output):
    require(len(output.encode('utf-8')) <= MAX_BYTES, 'XML response exceeds byte limit.', 502)
    text = unfence(output)
    require(not text.lstrip().startswith('<?xml'), 'XML declarations are not allowed.', 502)
    parser = DefusedXMLParser(target=BoundedTree(), forbid_dtd=True, forbid_entities=True, forbid_external=True)
    try:
        parser.feed(text)
        return parser.close()
    except (ParseError, DefusedXmlException) as error:
        raise DomainError('The summary is not a permitted, complete XML document.', 502) from error


def container(node, tag, attributes=None):
    require(node.tag == tag and node.attrib == (attributes or {}), f'Unexpected XML {tag} shape.', 502)
    require(not (node.text or '').strip() and all(not (child.tail or '').strip() for child in node),
            f'Unexpected prose inside XML {tag}.', 502)


def scalar(node, tag):
    require(node.tag == tag and not node.attrib and len(node) == 0, f'Invalid XML {tag} value.', 502)
    return node.text or ''


def terms(node, container_tag, item_tag):
    container(node, container_tag)
    return [scalar(child, item_tag) for child in node]


def parse_item(node):
    require(set(node.attrib) == {'source'}, 'A summary item needs exactly one source attribute.', 502)
    container(node, 'item', node.attrib)
    children = {child.tag: child for child in node}
    require(len(children) == len(node) and set(children) <= {'summary', 'quotes', 'topics', 'aliases'}
            and {'summary', 'quotes'} <= set(children), 'Missing, duplicated or unknown XML item fields.', 502)
    return {'source_id': node.attrib['source'], 'summary': scalar(children['summary'], 'summary'),
            'quotes': terms(children['quotes'], 'quotes', 'quote'),
            'topics': terms(children['topics'], 'topics', 'topic') if 'topics' in children else [],
            'aliases': terms(children['aliases'], 'aliases', 'alias') if 'aliases' in children else []}


def parse_summary_xml(output):
    root = parse_tree(output)
    container(root, 'scribe', {'task': 'summary'})
    require(len(root) == 1, 'XML summary requires exactly one items container.', 502)
    container(root[0], 'items')
    return {'items': [parse_item(item) for item in root[0]]}
