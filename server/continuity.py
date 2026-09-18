"""Continuity is derived only from commits on the selected message ancestry."""
from server.database import decode, encode, many
from server.memory.plan_state import author_edits
from server.memory.planned_events import plan_entry_fields


def continuity_rows(connection, head_id, author_version=None):
    path = many(connection, 'WITH RECURSIVE path AS (SELECT id,parent_id,0 AS depth FROM nodes WHERE id=? '
                'UNION ALL SELECT n.id,n.parent_id,p.depth+1 FROM nodes n JOIN path p ON p.parent_id=n.id) '
                'SELECT * FROM path', (head_id,))
    depths = {node['id']: node['depth'] for node in path}
    rows = many(connection, 'WITH RECURSIVE path AS (SELECT id,parent_id FROM nodes WHERE id=? '
                'UNION ALL SELECT n.id,n.parent_id FROM nodes n JOIN path p ON p.parent_id=n.id) '
                'SELECT c.* FROM continuity_commits c JOIN path p ON p.id=c.node_id', (head_id,))
    edits = [{**row, 'summary': '', 'source': 'author'} for row in author_edits(connection, author_version, head_id)]
    # Stable sorting puts the scene first, then oldest-to-newest author edits at the same node.
    return sorted([*rows, *edits], key=lambda row: -depths[row['node_id']])


def continuity_view(connection, head_id, author_version=None):
    rows = continuity_rows(connection, head_id, author_version)
    entries = {}
    commits = []
    for row in rows:
        changes = decode(row['changes'])
        commits.append({**row, 'changes': changes})
        for change in changes:
            entry_id = change['target_id'] or f"{row['origin_id']}:{change['id']}"
            entries[entry_id] = {'id': entry_id, 'kind': change['kind'], 'subject': change['subject'],
                                 'text': change['text'], 'status': 'resolved' if change['action'] == 'resolve' else 'active',
                                 'node_id': row['node_id'], 'commit_id': row['id'], 'evidence': change['evidence'],
                                 **plan_entry_fields(change)}
    return {'entries': list(entries.values()), 'commits': commits}


def continuity_values(item):
    keys = ('id', 'kind', 'subject', 'text', 'status', 'plan')
    return {key: item[key] for key in keys if key in item}


def continuity_sources(view):
    return [{'id': f"continuity:{item['id']}", 'kind': 'accepted continuity',
             'title': f"{item['kind']}: {item['subject']}",
             'text': encode({key: value for key, value in continuity_values(item).items() if key != 'id'})}
            for item in view['entries']]
