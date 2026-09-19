"""Bind search descriptions and plan-history groups to frozen accepted records."""
from server.archives.writer_summary_aids import validate_writer_aids
from server.continuity import continuity_view
from server.errors import require


def group_context(connection, snapshot, scope, content, archive):
    policy = content['story']['settings']['memory']
    aids = archive.get('summary_aids', {})
    require(isinstance(aids, dict) and (policy.get('summary_recall') is True or not aids),
            'Prewriting descriptions are outside the frozen summary policy.')
    sources = {source['id']: source for source in archive['sources']}
    require(aids.keys() <= sources.keys(), 'A search description refers to an excluded or missing original.')
    evidence = [sources[identity] for identity in aids]
    memory = {'receipt_version': 3, 'summary_aids': [{'chunk_id': identity, **aid} for identity, aid in aids.items()]}
    require(validate_writer_aids(connection, scope, memory, evidence), 'Search descriptions lack verifiable source identities.')
    continuity = continuity_view(connection, snapshot['branch']['head_id'], snapshot.get('continuity_version_id'))
    frozen_ids = {node['id']: scope.identities.node_id(node, scope.namespace) for node in scope.path}
    commits = [{**commit, 'node_id': frozen_ids[commit['node_id']]} for commit in continuity['commits']]
    return {**content, 'continuity': {**continuity, 'commits': commits}}
