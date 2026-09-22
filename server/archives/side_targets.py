from server.archives.format import SIDE_CONTEXT_TABLES, V46_TABLES
from server.archives.links import owned, snapshot_links
from server.archives.text_edits import validate_snapshot
from server.branches import path_nodes
from server.database import decode, encode, one
from server.errors import require
from server.side_targets import freeze
from server.text_edits.models import TextSelection
from server.text_edits.selection import apply_selection


def upgrade_side_targets(document):
    if document['version'] == 46:
        require(set(document['data']) == set(V46_TABLES), 'Version 46 needs its original record groups.')
        require(all('context_id' not in decode(row['snapshot']) and 'model_context' not in decode(row['snapshot']) for row in document['data']['side_turns']),
                'Version 46 does not include Companion context selections.')
        document['data'].update({key: [] for key in SIDE_CONTEXT_TABLES})
        document['version'] = 47
    return document


def validate_context(connection, row):
    snapshot = decode(row['snapshot'])
    require(set(snapshot) - {'origin_turn_id'} == {'version', 'branch', 'story_revision', 'target', 'sources', 'model_context'} and snapshot['version'] == 1,
            'Unsupported Companion context snapshot.')
    owned(connection, 'side_threads', row['thread_id'], row['story_id'])
    snapshot_links(connection, snapshot, row['story_id'])
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (snapshot['branch']['id'],))
    story = one(connection, 'SELECT revision FROM stories WHERE id=?', (row['story_id'],))
    require(type(snapshot['story_revision']) is int and 0 <= snapshot['story_revision'] <= story['revision'], 'A pinned Story revision is invalid.')
    require(type(snapshot['branch']['revision']) is int and 0 <= snapshot['branch']['revision'] <= branch['revision'], 'A pinned branch revision is invalid.')
    require(snapshot['branch']['head_id'] is None or snapshot['branch']['head_id'] in {node['id'] for node in path_nodes(connection, branch['head_id'], include_removed=True)},
            'A pinned context head is outside its source telling.')
    sources = snapshot['sources']
    require(isinstance(sources, list) and all(isinstance(item, dict) and all(isinstance(item.get(key), str) for key in ('id', 'title', 'text')) for item in sources),
            'Pinned source documents must contain literal source identities and text.')
    require(len({item['id'] for item in sources}) == len(sources), 'Pinned source identities must be unique.')
    validate_target(connection, snapshot['target'], snapshot, row['story_id'])
    expected = freeze(snapshot['branch'], snapshot['story_revision'], snapshot['target'], sources)['model_context']
    require(snapshot['model_context'] == expected, 'Pinned discussion instructions differ from the selected text and scope.')
    if 'origin_turn_id' in snapshot:
        original = one(connection, 'SELECT t.*,c.story_id FROM side_turns t JOIN side_threads c ON t.thread_id=c.id WHERE t.id=?', (snapshot['origin_turn_id'],))
        source = decode(original['snapshot'])
        require(original['story_id'] == row['story_id'] and snapshot['branch'] == source['branch'] and snapshot['sources'] == source['sources'],
                'An earlier context pin changed its original question sources.')
        if source.get('context_id'):
            source_context = decode(one(connection, 'SELECT snapshot FROM side_contexts WHERE id=?', (source['context_id'],))['snapshot'])
            require(snapshot['target'] == source_context['target'], 'An earlier context pin changed its original text selection.')
    return snapshot


def validate_target(connection, target, snapshot, story_id):
    kind = target['kind']
    keys = {'branch': {'kind'}, 'text': {'kind', 'snapshot', 'selection'}, 'comparison': {'kind', 'comparison'}, 'turn': {'kind', 'turn_id'}}
    extra = {'comparison'} if kind == 'text' and 'comparison' in target else set()
    require(kind in keys and set(target) == keys[kind] | extra, 'A Companion context has an unsupported target.')
    if kind == 'text':
        validate_snapshot(connection, target['snapshot'], story_id)
        require(target['snapshot']['ref'].get('branch_id') in {None, snapshot['branch']['id']}, 'A selected text target uses another telling.')
        selection = TextSelection.model_validate(target['selection'])
        apply_selection(target['snapshot']['text'], selection, 'replace', selection.text)
    if 'comparison' in target:
        from server.branch_tools.comparisons import comparison_view
        record = owned(connection, 'branch_comparisons', target['comparison']['id'], story_id)
        expected = comparison_view(connection, record)
        require(target['comparison']['story_id'] == story_id, 'A comparison target crosses Stories.')
        for side in ('left', 'right'):
            require(all(target['comparison'][side][key] == expected[side][key] for key in ('branch_id', 'head_id', 'revision', 'name')),
                    'A pinned comparison differs from its saved source paths.')
        choices = ('left', 'right') if kind == 'text' else ('left',)
        require(any(snapshot['branch']['id'] == record[f'{side}_branch_id'] and snapshot['branch']['head_id'] == record[f'{side}_head_id']
                    and snapshot['branch']['revision'] == record[f'{side}_revision'] for side in choices), 'A pinned comparison changed its source revision.')
    elif kind == 'turn':
        row = one(connection, 'SELECT t.snapshot,c.story_id FROM side_turns t JOIN side_threads c ON t.thread_id=c.id WHERE t.id=?', (target['turn_id'],))
        original = decode(row['snapshot'])
        require(row['story_id'] == story_id and snapshot['branch'] == original['branch'] and snapshot['sources'] == original['sources']
                and snapshot['story_revision'] == original['story_revision'], 'An earlier reply pin differs from its frozen context.')


def validate_side_targets(connection, data):
    contexts = {row['id']: (row, validate_context(connection, row)) for row in data['side_contexts']}
    for head in data['side_context_heads']:
        require(head['context_id'] is None or contexts[head['context_id']][0]['thread_id'] == head['thread_id'], 'A context head belongs to another conversation.')
    for turn in data['side_turns']:
        snapshot = decode(turn['snapshot'])
        if snapshot.get('context_id'):
            row, context = contexts[snapshot['context_id']]
            require(row['thread_id'] == turn['thread_id'] and snapshot['branch'] == context['branch']
                    and snapshot['model_context'] == context['model_context'], 'A question changed its pinned source target.')
        else:
            require('model_context' not in snapshot, 'A question has a target without its saved context identity.')


def remap_context(connection, row, mapping):
    from server.archives.remap import fields
    from server.archives.text_edit_versions import bind_restored_editions
    from server.archives.text_edits import remap_text_edit
    value = decode(row['snapshot'])
    if 'origin_turn_id' in value:
        value['origin_turn_id'] = mapping[value['origin_turn_id']]
    value['branch'] = fields(value['branch'], mapping)
    target = value['target']
    if target['kind'] == 'text':
        changed = remap_text_edit('text_edit_proposals', {'target': encode(target['snapshot'])}, mapping)
        target['snapshot'] = decode(bind_restored_editions(connection, 'text_edit_proposals', changed)['target'])
    elif target['kind'] == 'turn':
        target['turn_id'] = mapping[target['turn_id']]
    if 'comparison' in target:
        comparison = target['comparison']
        target['comparison'] = {**fields(comparison, mapping), **{side: fields(comparison[side], mapping) for side in ('left', 'right')}}
    return {**fields(row, mapping), 'snapshot': encode(value)}
