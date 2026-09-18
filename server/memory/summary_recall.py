"""Reviewed derivations support optional retrieval and explicitly enabled condensation."""
from server.database import decode, many
from server.memory.settings import memory_settings
from server.memory.summary_versions import applicable_versions


def summary_dependencies(connection, story):
    policy = memory_settings(decode(story['settings']).get('memory'))
    if policy.mode != 'long' or not (policy.summary_recall or policy.summary_context):
        return []
    # Cheap conservative invalidation: even a publication elsewhere in this Story
    # requires a fresh preview. No full manuscript traversal under a write lock.
    return [row['id'] for row in many(connection,
        'SELECT v.id FROM summary_versions v JOIN branches b ON b.id=v.branch_id WHERE b.story_id=? ORDER BY v.rowid',
        (story['id'],))]


def reviewed_aids(connection, branch, policy):
    if policy.mode != 'long' or not (policy.summary_recall or policy.summary_context):
        return {}
    seen, aids = set(), {}
    for version in applicable_versions(connection, branch).values():
        if version['origin'] != 'reviewed':
            continue
        proposals = {item['source_id']: item for item in version['result']['items']}
        for link in version['source_links']:
            chunk_id = f"message:{link['node_id']}@{link['start']}:{link['end']}:{link['sha256'][:12]}"
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            proposal = proposals.get(link['id'])
            if version['enabled'] and proposal:
                aids[chunk_id] = {**proposal, 'version_id': version['id'], 'source_sha256': link['sha256']}
    return aids
