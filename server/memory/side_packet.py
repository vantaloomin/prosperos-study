"""Freeze a common starting packet; later archive reads replace its working set."""
import hashlib

from server.database import decode, encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.side_archive import classify_archive, discussion_documents, permitted_sources
from server.memory.side_search import SourceArchive
from server.providers.capabilities import input_capacity
from server.side_work import effective_prompt, work_context

PROTOCOL = {
    'version': 1,
    'search': 'SEARCH_SOURCES: {"query":"terms to find","offset":0}',
    'list': 'LIST_SOURCES: {"offset":0}',
    'read': 'READ_SOURCES: [{"id":"exact source ID","offset":0,"length":1600}]',
    'rules': ('Return only one command, or an ordinary answer. Reads accept 1–8 IDs or ranges; '
              'a bare ID reads its first 1600 characters. Length is 1–2400 characters. '
              'Follow next_offset for result pages and end/has_more for exact source ranges. '
              'Each command replaces the working source window and consumes one permitted additional pass. '
              'The full permitted archive stays available. Discovery snippets are partial evidence, not complete sources. '
              'No file, network, story mutation or acceptance operations exist. Omitted material is unknown.')
}


def packet_base(snapshot):
    return {'question': snapshot['question'], 'disclosure': snapshot['disclosure'],
            'conversation': snapshot['retrieval']['conversation'],
            'conversation_coverage': snapshot['retrieval']['conversation_coverage'],
            'retrieval_protocol': snapshot['retrieval']['protocol'], 'archive_source_count': len(permitted_sources(snapshot)),
            **({'selected_context': snapshot['model_context']} if 'model_context' in snapshot else {}), **work_context(snapshot)}


def fits(snapshot, content):
    limits = snapshot['retrieval']
    return token_estimate(effective_prompt(snapshot), content) <= limits['input_allowance'] - limits['overhead_margin']


def packet(snapshot, discovery, sources=()):
    page = {**discovery, 'results': list(discovery['results'])}
    base = {**packet_base(snapshot), 'source_index': page['results'], 'sources': list(sources),
            'discovery': {key: value for key, value in page.items() if key != 'results'}}
    while not fits(snapshot, base) and base['source_index']:
        base['source_index'].pop()
        base['discovery']['next_offset'] = page['offset'] + len(base['source_index'])
    require(fits(snapshot, base), 'The question, discussion or requested read ranges exceed the model allowance. '
            'Use shorter read ranges, fewer sources, a narrower question or a larger profile.', 409)
    require(not discovery['results'] or bool(base['source_index']), 'The question and discussion leave no room for archive discovery. Ask a shorter question or use a larger profile.', 409)
    return encode(base)


def prepare_archive(snapshot, history, profiles):
    documents, conversation = discussion_documents(history)
    allowance = min(input_capacity(profile['config']) for profile in profiles)
    sources = {item['id']: item for item in [*classify_archive(snapshot['sources']), *documents]}
    archive = {**snapshot, 'sources': list(sources.values()),
               'retrieval': {'version': 1, 'protocol': PROTOCOL, 'input_allowance': allowance,
                             'overhead_margin': min(512, max(128, allowance // 50)),
                             'conversation': [], 'conversation_coverage': {}}}
    visible = [item for item in conversation if not item['private'] or snapshot['disclosure'] == 'full-disclosure']
    recent = []
    for item in reversed(visible[-2:]):
        trial = [{key: value for key, value in item.items() if key != 'private'}, *recent]
        cost = token_estimate('', trial)
        if cost > allowance // 3:
            break
        recent = trial
    archive['retrieval'].update(conversation=recent,
        conversation_coverage={'available_turns': len(visible), 'included_turns': len(recent),
                               'earlier_discussion': 'Available through archive search; never accepted Story memory.'})
    while recent and not fits(archive, {**packet_base(archive), 'source_index': [], 'sources': []}):
        recent.pop(0)
        archive['retrieval']['conversation_coverage']['included_turns'] = len(recent)
    search = SourceArchive(archive).search(snapshot['question'][:1000])
    content = packet(archive, search)
    archive['retrieval']['initial_content'] = content
    archive['initial_source_ids'] = []
    return archive


def next_packet(snapshot, archive, request):
    kind, value = request
    if kind == 'READ_SOURCES':
        page = {'query': '', 'offset': 0, 'total': 0, 'next_offset': None, 'results': []}
        return packet(snapshot, page, archive.read(value))
    return packet(snapshot, archive.search(**value))


def read_receipts(context):
    fragments = [*context['source_index'], *context['sources']]
    return [{'id': source['id'], 'start': source['start'], 'end': source['end'],
             'sha256': source['sha256'], 'total_chars': source['total_chars'],
             'kind': 'discovery' if index < len(context['source_index']) else 'read',
             **({'recall_aid': source['recall_aid']} if 'recall_aid' in source else {})}
            for index, source in enumerate(fragments)]


def request_receipt(content):
    context = decode(content)
    receipts = read_receipts(context)
    return {'content': content, 'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
            'source_ids': list(dict.fromkeys(item['id'] for item in receipts)), 'read_receipts': receipts,
            'reported': {}}
