"""Verify tentative extraction receipts and their exact frozen source dependencies."""
from server.archives.identities import SourceIdentities, records
from server.branches import path_nodes
from server.database import decode, encode, one
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.control_state import controls_at
from server.memory.relationship_context import MAX_SOURCES, extraction_profile
from server.memory.relationship_output import MAX_OUTPUT, PROMPT, VERSION, parse_annotations
from server.memory.relationship_sources import annotations_from_job, story_jobs
from server.memory.writer_recall import digest


def validate_source(source, link, path, identities):
    require(set(link) == {'id', 'node_id', 'start', 'end', 'sha256'} and link['node_id'] in path,
            'A relationship dependency is outside its saved path.')
    node, position = path[link['node_id']]
    require(node['role'] != 'ooc' and identities.matches(node['id'], source['node_id']), 'Invalid relationship prose identity.')
    chunks = compile_chunks(f"message:{source['node_id']}", f"{node['role']} passage", node['text'])
    expected = next((chunk for chunk in chunks if chunk.id == source['id']), None)
    require(expected is not None and source == {**expected.evidence(), 'node_id': source['node_id'], 'passage_number': position},
            'Relationship input differs from an exact canonical source chunk.')
    require(all(source[key] == link[key] for key in ('id', 'start', 'end', 'sha256')), 'Relationship source coordinates differ.')


def validate_scope(connection, snapshot, content, identities):
    branch = snapshot['branch']
    actual = one(connection, 'SELECT story_id FROM branches WHERE id=?', (branch['id'],))
    require(actual['story_id'] == branch['story_id'], 'Relationship preparation crosses Stories.')
    nodes = path_nodes(connection, branch['head_id'])
    require(all(node['story_id'] == branch['story_id'] for node in nodes), 'Relationship sources cross Stories.')
    path = {node['id']: (node, index) for index, node in enumerate(nodes, 1)}
    sources, links = content['sources'], snapshot['source_links']
    require(1 <= len(sources) <= MAX_SOURCES and len(sources) == len(links)
            and len({source['id'] for source in sources}) == len(sources), 'Invalid relationship source count.')
    for source, link in zip(sources, links, strict=True):
        validate_source(source, link, path, identities)
    target = next((source for source in sources if source['id'] == content['target_id']), None)
    require(target is not None and content['target_id'] == snapshot['target_id'], 'Missing relationship target.')
    require(all((source['passage_number'], source['start']) <= (target['passage_number'], target['start']) for source in sources),
            'Relationship extraction contains sources after its target.')
    controls = controls_at(connection, branch, snapshot['memory_controls_version_id'])
    excluded = {(source['node_id'], source['start'], source['end'], source['sha256'])
                for entry in controls['entries'] if entry['enabled'] and entry['kind'] == 'emphasis' and entry['stance'] == 'exclude'
                for source in entry['sources']}
    require(not any((link['node_id'], link['start'], link['end'], link['sha256']) in excluded for link in links),
            'Relationship preparation includes an excluded source.')


def validate_job(connection, job, identities):
    snapshot = decode(job['snapshot'])
    require(snapshot['version'] == VERSION and snapshot['prompt_text'] == PROMPT
            and snapshot['branch']['id'] == job['branch_id'] and job['mode'] in {'manual', 'automatic'},
            'Unsupported relationship request.')
    profile = snapshot['profile']
    saved = one(connection, 'SELECT * FROM profile_versions WHERE id=?', (profile['id'],))
    require(saved['profile_id'] == profile['profile_id'] and decode(saved['config']) == profile['config'],
            'Relationship model differs from its saved configuration.')
    content = decode(snapshot['content'])
    require(set(content) == {'task', 'target_id', 'sources'}
            and content['task'] == 'Find tentative event and relationship search aids.', 'Unsupported annotation input.')
    key = digest(encode({'version': VERSION, 'content': content, 'profile': profile['config']}))
    require(job['request_key'] == snapshot['request_key'] == key, 'Relationship request fingerprint changed.')
    config = extraction_profile(profile)['config']
    require(token_estimate(PROMPT, content) + 256 <= config['context_tokens'] - config['max_output_tokens'],
            'Relationship preparation exceeds its allowance.')
    validate_scope(connection, snapshot, content, identities)
    validate_result(job, snapshot)


def validate_result(row, snapshot):
    require(row['status'] in {'queued', 'running', 'done', 'error', 'cancelled', 'interrupted'}
            and isinstance(row['output'], str) and len(row['output']) <= MAX_OUTPUT, 'Invalid relationship result state.')
    if row['status'] == 'done':
        require(decode(row['result']) == parse_annotations(row['output'], snapshot), 'Relationship grounding changed.')
    else:
        require(decode(row['result']) is None, 'Incomplete extraction cannot claim annotations.')


def validate_relationships(connection, data):
    identities = SourceIdentities(connection, records(data))
    jobs = {row['id']: row for row in data['relationship_jobs']}
    for job in jobs.values():
        validate_job(connection, job, identities)
    for attempt in data['relationship_attempts']:
        validate_result(attempt, decode(jobs[attempt['job_id']]['snapshot']))


def validate_annotation_aids(connection, snapshot, scope, identities):
    archive = snapshot['writer_recall']
    aids = archive.get('annotation_aids', [])
    policy = decode(snapshot['content'])['story']['settings']['memory']
    require(isinstance(aids, list) and (policy.get('relationship_recall') is True or not aids),
            'Relationship aids are outside the saved recall policy.')
    jobs = story_jobs(connection, snapshot['branch'])
    nodes = {node['id']: node for node in scope.path}
    def translate(identity):
        return identities.node_id(nodes[identity], scope.namespace) if identity in nodes else 'outside'
    seen = set()
    for aid in aids:
        key = (aid['job_id'], aid['ordinal'])
        require(key not in seen, 'Duplicate relationship annotation.')
        seen.add(key)
        job = next((row for row in jobs if identities.matches(row['id'], aid['job_id'])), None)
        require(job is not None, 'A relationship aid lacks its preparation receipt.')
        expected = [{**item, 'job_id': aid['job_id']} for item in annotations_from_job(job, archive['sources'], translate)]
        require(aid in expected, 'A relationship aid changed or lost a permitted source dependency.')
    return aids
