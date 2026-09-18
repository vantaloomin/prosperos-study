"""Classify and scope the frozen sidebar archive before discovery or ranking."""
import json

from server.database import encode

PRIVATE_KEYS = {'private_background', 'background_state_id', 'selected_private_interpretation'}


def contains_private(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if any(item.get(key) for key in PRIVATE_KEYS):
                return True
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and item.lstrip().startswith(('{', '[')):
            try:
                pending.append(json.loads(item))
            except (ValueError, RecursionError):
                # An explicitly marked but unreadable private payload stays private.
                if any(key in item for key in PRIVATE_KEYS):
                    return True
    return False


def authority(source_id):
    if ':message:' in source_id:
        return 'Selected path contribution; the title identifies its branch and role.'
    if source_id.startswith('continuity:'):
        return 'Accepted continuity from the selected path.'
    if source_id.startswith(('asset:', 'import:')):
        return 'Pinned Library material; inspect its enabled state and rules before treating it as active Canon.'
    if source_id.startswith('discussion:'):
        return 'Side discussion only; suggestions are not accepted Story events.'
    return 'Configuration or recorded workflow material; proposals and alternatives are not accepted Story events.'


def classify_archive(documents):
    groups = {}
    for document in documents:
        group = document['id'].rsplit(':', 1)[0]
        groups.setdefault(group, []).append(document)
    private = {group for group, items in groups.items()
               if group.startswith(('background:', 'private-interpretation:'))
               or contains_private(''.join(item['text'] for item in items))}
    return [{**item, 'private': item['id'].rsplit(':', 1)[0] in private,
             'authority': authority(item['id'])} for item in documents]


def permitted_sources(snapshot):
    if not snapshot.get('retrieval') or snapshot['disclosure'] == 'full-disclosure':
        return snapshot['sources']
    return [item for item in snapshot['sources'] if not item.get('private')]


def discussion_documents(history):
    documents, conversation = [], []
    for row in history:
        original = json.loads(row['snapshot'])
        private = private_discussion(original, row)
        turn = {'question': row['question'], 'answer': row['output'], 'branch': original['branch']['name']}
        text = encode(turn)
        source_id = f"discussion:{row['id']}"
        title = f"Side discussion on {turn['branch']}"
        documents.extend({'id': f'{source_id}:{offset // 6000 + 1}', 'title': title,
                          'text': text[offset:offset + 6000], 'private': private,
                          'authority': authority(source_id)} for offset in range(0, len(text), 6000))
        conversation.append({**turn, 'private': private})
    return documents, conversation


def private_discussion(original, row):
    if original['disclosure'] == 'full-disclosure':
        return True
    read = set(json.loads(row.get('coverage', '[]')))
    if not read:
        return False
    sources = original.get('sources', [])
    classified = sources if original.get('retrieval') else classify_archive(sources)
    return any(item['id'] in read and item.get('private') for item in classified)
