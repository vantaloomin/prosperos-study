"""Bounded extraction inputs: a new target and earlier permitted originals."""
from server.database import decode, encode, one
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.relationship_output import PROMPT, VERSION
from server.memory.relationship_sources import (
    active_annotations,
    job_sources,
    source_catalog,
    story_jobs,
    story_policy,
)
from server.memory.writer_recall import digest
from server.memory.writer_recall_packet import search_sources
from server.profiles import resolve_profile
from server.providers.capabilities import input_capacity
from server.stories import check_revision

MAX_REQUESTS = 4
MAX_SOURCES = 8


def extraction_profile(profile):
    return {**profile, 'config': {**profile['config'], 'max_output_tokens': min(1200, profile['config']['max_output_tokens']),
                                'timeout_seconds': min(60, profile['config']['timeout_seconds'])}}


def processed_targets(jobs, sources, profile):
    processed = set()
    for job in jobs:
        snapshot = decode(job['snapshot'])
        if snapshot['profile']['config'] != profile['config']:
            continue
        matched = job_sources(job, sources)
        if matched is not None:
            processed.add(matched[snapshot['target_id']]['id'])
    return processed


def anchors(target, earlier, aids):
    indexed = {source['id']: source for source in earlier}
    hits = search_sources(earlier, [target['text']])
    # Recent context helps interpret pronouns during extraction, not automatic recall expansion.
    candidates = [hit.chunk.id for hit in hits[:3]] + [source['id'] for source in earlier[-2:]]
    for aid in reversed(aids):
        if aid['kind'] in {'intention', 'relationship'}:
            candidates.extend(citation['source_id'] for citation in aid['evidence'])
    candidates.extend(hit.chunk.id for hit in hits[3:])
    return [indexed[identity] for identity in dict.fromkeys(candidates) if identity in indexed][:MAX_SOURCES - 1]


def request_snapshot(branch, profile, controls, target, earlier, aids):
    supporting = anchors(target, earlier, aids)
    content = {'task': 'Find tentative event and relationship search aids.', 'target_id': target['id'],
               'sources': [target, *supporting]}
    prepared = extraction_profile(profile)
    allowance = input_capacity(prepared['config']) - 256
    while token_estimate(PROMPT, content) > allowance and supporting:
        supporting.pop()
        content['sources'] = [target, *supporting]
    require(token_estimate(PROMPT, content) <= allowance, 'The target passage does not fit this relationship model profile.', 409)
    sources = sorted(content['sources'], key=lambda row: (row['passage_number'], row['start']))
    content['sources'] = sources
    key = digest(encode({'version': VERSION, 'content': content, 'profile': profile['config']}))
    return {'version': VERSION, 'branch': branch, 'profile': profile, 'prompt_text': PROMPT,
            'request_key': key, 'target_id': target['id'], 'memory_controls_version_id': controls,
            'content': encode(content), 'source_links': [{key: row[key] for key in
                ('id', 'node_id', 'start', 'end', 'sha256')} for row in sources]}


def plan_requests(connection, branch_id, revision=None, node_ids=None):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    if revision is not None:
        check_revision(branch, revision)
    story, policy = story_policy(connection, branch)
    require(not story['archived'] and policy.mode == 'long' and policy.relationship_recall,
            'Enable relationship recall in Long story writing preferences first.', 409)
    if node_ids is not None:
        require(policy.relationship_automatic, 'Automatic relationship preparation is disabled.', 409)
    profile = resolve_profile(connection, story, 'writer')
    sources, controls = source_catalog(connection, branch)
    jobs = story_jobs(connection, branch)
    processed = processed_targets(jobs, sources, profile)
    selected = [source for source in sources if source['id'] not in processed
                and (node_ids is None or source['node_id'] in node_ids)][:MAX_REQUESTS]
    aids = active_annotations(connection, branch, sources)
    positions = {source['id']: index for index, source in enumerate(sources)}
    snapshots = [request_snapshot(branch, profile, controls, target, sources[:positions[target['id']]], aids)
                 for target in selected]
    return {'snapshots': snapshots, 'eligible': len(sources), 'prepared': len(processed),
            'remaining': len(sources) - len(processed) - len(selected)}
