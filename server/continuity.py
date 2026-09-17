"""Continuity is derived only from commits on the selected message ancestry."""
from server.database import decode, encode, many


def continuity_view(connection, head_id):
    rows = many(connection, 'WITH RECURSIVE path AS (SELECT id,parent_id,0 AS depth FROM nodes WHERE id=? '
                'UNION ALL SELECT n.id,n.parent_id,p.depth+1 FROM nodes n JOIN path p ON p.parent_id=n.id) '
                'SELECT c.* FROM continuity_commits c JOIN path p ON p.id=c.node_id ORDER BY p.depth DESC', (head_id,))
    entries = {}
    commits = []
    for row in rows:
        changes = decode(row['changes'])
        commits.append({**row, 'changes': changes})
        for change in changes:
            entry_id = change['target_id'] or f"{row['origin_id']}:{change['id']}"
            entries[entry_id] = {'id': entry_id, 'kind': change['kind'], 'subject': change['subject'],
                                 'text': change['text'], 'status': 'resolved' if change['action'] == 'resolve' else 'active',
                                 'node_id': row['node_id'], 'commit_id': row['id'], 'evidence': change['evidence']}
    return {'entries': list(entries.values()), 'commits': commits}


def continuity_sources(view):
    return [{'id': f"continuity:{item['id']}", 'kind': 'accepted continuity',
             'title': f"{item['kind']}: {item['subject']}",
             'text': encode({key: item[key] for key in ('kind', 'subject', 'text', 'status')})}
            for item in view['entries']]
