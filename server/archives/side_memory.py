"""Check exact sidebar read receipts without reranking its frozen archive."""
import hashlib

from server.database import decode
from server.errors import require
from server.memory.scoped_aids import aid_reference, validate_document_aid
from server.memory.side_archive import permitted_sources
from server.memory.side_packet import request_receipt


def validate_fragment(fragment, documents):
    require(isinstance(fragment, dict) and fragment.get('id') in documents, 'A sidebar read leaves its permitted frozen archive.')
    source = documents[fragment['id']]
    require(fragment.get('recall_aid') == aid_reference(source).get('recall_aid'), 'A sidebar read changed reviewed memory provenance.')
    start, end = fragment.get('start'), fragment.get('end')
    require(type(start) is int and type(end) is int and 0 <= start <= end <= len(source['text']),
            'A sidebar read has an invalid range.')
    text = source['text'][start:end]
    require(fragment.get('text') == text and fragment.get('sha256') == hashlib.sha256(text.encode()).hexdigest(),
            'A sidebar excerpt differs from its original source.')
    require(fragment.get('total_chars') == len(source['text']) and fragment.get('has_more') == (end < len(source['text'])),
            'A sidebar read has incorrect source coverage.')
    require(fragment.get('title') == source['title'][:240] and fragment.get('authority') == source.get('authority', ''),
            'A sidebar read has changed its source identity or authority.')


def validate_packet(content, snapshot, documents):
    from server.side_work import work_context
    context = decode(content)
    require(all(context.get(key) == value for key, value in work_context(snapshot).items()), 'A sidebar packet changed its author-selected task or style.')
    require(context.get('selected_context') == snapshot.get('model_context'), 'A sidebar request changed its selected context.')
    policy = snapshot['retrieval']
    require(context['question'] == snapshot['question'] and context['disclosure'] == snapshot['disclosure'],
            'A sidebar request differs from its frozen question or disclosure.')
    require(context['conversation'] == policy['conversation'] and context['conversation_coverage'] == policy['conversation_coverage']
            and context['retrieval_protocol'] == policy['protocol'], 'A sidebar request changed its frozen discussion or protocol.')
    require(context['archive_source_count'] == len(documents) and len(context['source_index']) <= 8
            and len(context['sources']) <= 8, 'A sidebar discovery page is outside its bounds.')
    for fragment in [*context['source_index'], *context['sources']]:
        validate_fragment(fragment, documents)


def validate_reply(reply, snapshot, documents):
    usage = decode(reply['usage'])
    coverage = set()
    for index, item in enumerate(usage):
        require('content' in item, 'A sidebar request is missing its exact inputs.')
        validate_packet(item['content'], snapshot, documents)
        expected = request_receipt(item['content'])
        require(all(item.get(key) == value for key, value in expected.items() if key != 'reported'),
                'A sidebar read receipt differs from its preserved request.')
        if index == 0:
            require(item['content'] == snapshot['retrieval']['initial_content'], 'A sidebar reply changed its common starting inputs.')
        coverage.update(item['source_ids'])
    require(sorted(coverage) == decode(reply['coverage']), 'Sidebar coverage does not match its request receipts.')


def validate_side_memory(data):
    turns = {row['id']: decode(row['snapshot']) for row in data['side_turns']}
    for turn in turns.values():
        if not turn.get('retrieval'):
            continue
        require(turn['retrieval'].get('version') == 1, 'Unsupported sidebar archive retrieval version.')
        for document in turn['sources']:
            validate_document_aid(document)
        documents = {item['id']: item for item in permitted_sources(turn)}
        validate_packet(turn['retrieval']['initial_content'], turn, documents)
    for reply in data['side_replies']:
        snapshot = turns[reply['turn_id']]
        if snapshot.get('retrieval'):
            documents = {item['id']: item for item in permitted_sources(snapshot)}
            validate_reply(reply, snapshot, documents)
