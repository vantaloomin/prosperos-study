"""Bind consumed derived context to a reviewed edition and its exact permitted source."""
import hashlib

from server.branches import path_nodes
from server.database import decode, one
from server.errors import require
from server.memory.summary_excerpt import KIND, aid_items, summary_excerpt, summary_items


def validate_summary_context(connection, snapshot, branch, policy):
    content = decode(snapshot['content'])
    items = summary_items(content)
    links = snapshot.get('summary_links', [])
    require(isinstance(links, list) and len(items) == len(links), 'Derived context has missing source bindings.')
    if not items:
        memory = snapshot.get('memory') or snapshot.get('source_memory') or {}
        require(not memory.get('summary_context') and not memory.get('coverage', {}).get('summarized_passages')
                and memory.get('algorithm') not in {'prospero-lexical-v7-summary-context', 'prospero-source-summaries-v7'},
                'A summary receipt has no corresponding derived context.')
        return
    require(policy.get('mode') == 'long' and policy.get('summary_context') is True
            and content.get('scope') != 'blind', 'Derived summaries are outside this request policy or role.')
    memory = snapshot.get('memory') or snapshot.get('source_memory') or {}
    require(hashlib.sha256(snapshot['content'].encode()).hexdigest() == memory.get('content_sha256'),
            'Derived context differs from its frozen input receipt.')
    require(len({link['id'] for link in links}) == len(links), 'Derived context source bindings are duplicated.')
    path = path_nodes(connection, branch['head_id'])
    nodes = {node['id']: node for node in path}
    for item, link in zip(items, links, strict=True):
        validate_consumed(connection, item, link, nodes, path)
    validate_summary_coverage(content, memory)


def validate_consumed(connection, item, link, nodes, path):
    require(set(link) == {'id', 'version_id', 'frozen_version_id', 'node_id', 'frozen_source_id'}
            and link['node_id'] in nodes, 'A derived context binding leaves the permitted path.')
    require(item['id'] == link['id'] and item['source_id'] == link['frozen_source_id']
            and item['summary_version_id'] == link['frozen_version_id'], 'A derived item changed its frozen source identity.')
    version = one(connection, 'SELECT * FROM summary_versions WHERE id=?', (link['version_id'],))
    require(version['origin'] == 'reviewed' and version['enabled'] == 1 and version['node_id'] in nodes,
            'Derived context uses an unreviewed, disabled or future summary edition.')
    run = decode(one(connection, 'SELECT snapshot FROM summary_runs WHERE id=?', (version['run_id'],))['snapshot'])
    require(all(source['node_id'] in nodes for source in run['source_links']), 'A consumed summary depends on another path.')
    source = next((source for source in run['source_links'] if source_matches(source, item, link)), None)
    require(source is not None, 'A reviewed interpretation refers to different source coordinates.')
    node = nodes[link['node_id']]
    text = node['text'][item['start']:item['end']]
    require(node['role'] != 'ooc' and hashlib.sha256(text.encode()).hexdigest() == item['sha256'],
            'A reviewed interpretation no longer matches exact accepted prose.')
    proposal = next((row for row in decode(version['result'])['items'] if row['source_id'] == source['id']), None)
    require(proposal is not None, 'A derived interpretation was not published in its claimed edition.')
    expected = summary_excerpt(item['source_id'], item['start'], item['end'], item['sha256'],
                               {**proposal, 'version_id': link['frozen_version_id']})
    if 'passage_number' in item:
        expected['passage_number'] = next(i + 1 for i, row in enumerate(path) if row['id'] == link['node_id'])
    if item['kind'] == 'review evidence':
        expected['kind'] = 'review evidence'  # The interpretation label/authority remains on carried evidence.
    require(item == expected, 'A consumed summary differs from its reviewed text, quotations or authority label.')


def source_matches(source, item, link):
    return source['node_id'] == link['node_id'] and all(source[key] == item[key] for key in ('start', 'end', 'sha256'))


def validate_summary_coverage(content, memory):
    if 'reviewed_summaries' not in content:
        return  # Specialist selection coverage is checked by source_replay.
    items = content['reviewed_summaries']
    expected = [{key: item[key] for key in ('id', 'source_id', 'start', 'end', 'sha256', 'summary_version_id')} for item in items]
    require(memory.get('algorithm') == 'prospero-lexical-v7-summary-context' and memory.get('receipt_version') == 4
            and memory.get('summary_context') == expected, 'Writer summary receipt disagrees with its supplied interpretations.')
    require(memory.get('coverage', {}).get('summarized_messages') == len({item['source_id'] for item in items})
            and all(item['kind'] == KIND for item in items), 'Writer summary coverage or authority was altered.')


def validate_writer_summaries(connection, data):
    snapshots = [decode(row['snapshot']) for row in data['generations']]
    snapshots.extend(decode(row['snapshot'])['writer_snapshot'] for row in data['assessment_runs'])
    for snapshot in snapshots:
        content = decode(snapshot['content'])
        policy = content.get('story', {}).get('settings', {}).get('memory', {})
        validate_summary_context(connection, snapshot, snapshot['branch'], policy)


def validate_scene_bindings(connection, origin):
    if not origin.get('memory_policy', {}).get('summary_context'):
        require(not origin.get('summary_aid_links'), 'Summary bindings exist outside the frozen scene policy.')
        return
    items = aid_items(origin['sources'], origin.get('summary_aids', {}))
    links = origin.get('summary_aid_links', [])
    require(len(items) == len(links), 'The scene has missing reviewed summary bindings.')
    path = path_nodes(connection, origin['branch']['head_id'])
    nodes = {node['id']: node for node in path}
    for item, link in zip(items, links, strict=True):
        validate_consumed(connection, item, link, nodes, path)
