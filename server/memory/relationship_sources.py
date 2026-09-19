"""Permitted originals and dependency checks for disposable relationship aids."""
from server.branches import path_nodes
from server.database import decode, many, one
from server.memory.chunks import compile_chunks
from server.memory.control_packet import decision_packet, excluded_chunks
from server.memory.control_state import control_view
from server.memory.settings import memory_settings
from server.memory.writer_recall import digest


def source_catalog(connection, branch):
    controls = control_view(connection, branch)
    blocked = excluded_chunks({'author_memory': decision_packet(controls) or {}})
    sources = [{**chunk.evidence(), 'node_id': node['id'], 'passage_number': position}
               for position, node in enumerate(path_nodes(connection, branch['head_id']), 1) if node['role'] != 'ooc'
               for chunk in compile_chunks(f"message:{node['id']}", f"{node['role']} passage", node['text'])
               if chunk.id not in blocked]
    return sources, controls['version_id']


def story_policy(connection, branch):
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    policy = memory_settings(decode(story['settings']).get('memory'))
    return story, policy


def job_sources(job, sources, translate=lambda identity: identity):
    """Map frozen citations to current permitted originals; every input is a dependency."""
    snapshot = decode(job['snapshot'])
    available = {(row['source_id'], row['start'], row['end'], row['sha256']): row for row in sources}
    matched = {}
    for link in snapshot['source_links']:
        key = (f"message:{translate(link['node_id'])}", link['start'], link['end'], link['sha256'])
        if key not in available:
            return None
        matched[link['id']] = available[key]
    return matched


def story_jobs(connection, branch):
    return many(connection, 'SELECT j.* FROM relationship_jobs j JOIN branches b ON b.id=j.branch_id '
                'WHERE b.story_id=? ORDER BY j.rowid DESC', (branch['story_id'],))


def annotations_from_job(job, sources, translate=lambda identity: identity):
    if job['status'] != 'done':
        return []
    matched = job_sources(job, sources, translate)
    if matched is None:
        return []
    result = decode(job['result'])
    return [{'job_id': job['id'], 'ordinal': ordinal, 'kind': item['kind'], 'relation': item['relation'],
             'description': item['description'], 'actor': item['actor'],
             'evidence': [{**citation, 'source_id': matched[citation['source_id']]['id']} for citation in item['evidence']]}
            for ordinal, item in enumerate(result['items'])]


def active_annotations(connection, branch, sources):
    seen, result = set(), []
    for job in story_jobs(connection, branch):
        matched = job_sources(job, sources)
        if matched is None:
            continue
        target = matched[decode(job['snapshot'])['target_id']]['id']
        if target in seen or job['status'] != 'done':
            continue
        seen.add(target)
        result.extend(annotations_from_job(job, sources))
    return result


def annotation_groups(aids, sources):
    from server.memory.evidence_groups import group_record
    return [group_record('relationship:' + digest(str(aid['job_id']) + ':' + str(aid['ordinal'])),
                        'derived relationship', 'Tentative ' + aid['relation'] + ' link (' + aid['kind'] + ')',
                        aid['actor'] + ' ' + aid['description'],
                        {citation['source_id'] for citation in aid['evidence']}, 0, sources) for aid in aids]
