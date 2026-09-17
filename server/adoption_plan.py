"""Resolve explicitly selected versions and expose every dependent change before adoption."""
import hashlib

from server.database import encode, many, one
from server.errors import require
from server.library import get_version
from server.manifests import attachments_at, dependencies_for


def selected_versions(connection, primary_id, additional_ids):
    versions = [get_version(connection, key) for key in [primary_id, *additional_ids]]
    selected = {version['asset_id']: version for version in versions}
    require(len(selected) == len(versions), 'Choose only one version of each Library item.')
    return selected


def requirements(connection, items):
    result = {}
    for item in items.values():
        parent = get_version(connection, item['version_id'])
        for dependency in dependencies_for(connection, item):
            result.setdefault(dependency['asset_id'], []).append((dependency, parent))
    return result


def dependency_conflict(connection, asset_id, demands, selected):
    requested = {item['version_id'] for item, _parent in demands}
    chosen = selected.get(asset_id)
    if len(requested) == 1 and (not chosen or chosen['id'] in requested):
        return None
    references = []
    for dependency, parent in demands:
        book = get_version(connection, dependency['version_id'])
        latest = one(connection, 'SELECT latest_version_id FROM assets WHERE id=?', (parent['asset_id'],))
        published = get_version(connection, latest['latest_version_id'])
        references.append({'asset_id': parent['asset_id'], 'version_id': parent['id'],
            'name': parent['name'], 'number': parent['number'], 'requires_number': book['number'],
            'latest_version_id': published['id'], 'latest_number': published['number']})
    name = get_version(connection, demands[0][0]['version_id'])['name']
    return {'asset_id': asset_id, 'name': name, 'references': references,
            'message': f'{name} has incompatible linked versions. Review the items that reference it.'}


def next_attachments(connection, current, selected):
    following, conflicts = dict(current), []
    for asset_id, demands in requirements(connection, current).items():
        conflict = dependency_conflict(connection, asset_id, demands, selected)
        if conflict:
            conflicts.append(conflict)
            continue
        dependency = demands[0][0]
        previous = current.get(asset_id, dependency)
        following[asset_id] = {**previous, 'version_id': dependency['version_id'], 'enabled': True}
    return following, conflicts


def resolve_attachments(connection, original, selected):
    current = {item['asset_id']: {**item, 'version_id': selected.get(item['asset_id'], {}).get('id', item['version_id'])}
               for item in original}
    seen = set()
    while True:
        signature = encode(sorted((key, value['version_id'], value['enabled']) for key, value in current.items()))
        if signature in seen:
            return list(current.values()), [{'asset_id': '', 'name': 'Linked lore', 'references': [],
                'message': 'Linked versions form a conflicting cycle. Revise their references before updating.'}]
        seen.add(signature)
        following, conflicts = next_attachments(connection, current, selected)
        if following == current:
            return sorted(current.values(), key=lambda item: (-item['priority'], item['asset_id'])), conflicts
        current = following


def change_view(connection, before, after, selected):
    previous = {item['asset_id']: item for item in before}
    changes = []
    for item in after:
        old = previous.get(item['asset_id'])
        if old == item:
            continue
        new_version = get_version(connection, item['version_id'])
        old_version = get_version(connection, old['version_id']) if old else None
        changes.append({'asset_id': item['asset_id'], 'name': new_version['name'],
            'before_version_id': old['version_id'] if old else None, 'after_version_id': item['version_id'],
            'old_version': old_version['number'] if old_version else None, 'new_version': new_version['number'],
            'enabled_before': old['enabled'] if old else None, 'enabled_after': item['enabled'],
            'reason': 'selected' if item['asset_id'] in selected else 'dependency'})
    return changes


def story_plan(connection, story, original, selected):
    updated, conflicts = resolve_attachments(connection, original, selected)
    changes = change_view(connection, original, updated, selected)
    matched = next(item for item in original if item['asset_id'] in selected)
    old = get_version(connection, matched['version_id'])
    new = selected[matched['asset_id']]
    return {'story_id': story['id'], 'title': story['title'], 'archived': bool(story['archived']),
            'expected_revision': story['revision'], 'manifest_id': story['manifest_id'],
            'old_version': old['number'], 'new_version': new['number'], 'changed': bool(changes),
            'changes': changes, 'conflicts': conflicts, 'attachments': updated}


def preview_versions(connection, selected, targets):
    ids = {version['id'] for version in selected.values()}
    for target in targets:
        for change in target['changes']:
            ids.update(key for key in (change['before_version_id'], change['after_version_id']) if key)
    return [get_version(connection, key) for key in sorted(ids)]


def build_preview(connection, version_id, additional_ids):
    selected = selected_versions(connection, version_id, additional_ids)
    targets = []
    for story in many(connection, 'SELECT * FROM stories ORDER BY id'):
        original = attachments_at(connection, story['manifest_id'])
        if any(item['asset_id'] in selected for item in original):
            targets.append(story_plan(connection, story, original, selected))
    digest = [{'story_id': item['story_id'], 'manifest_id': item['manifest_id'],
               'revision': item['expected_revision'], 'attachments': item['attachments']} for item in targets]
    return {'version': get_version(connection, version_id), 'targets': targets,
            'selected_versions': list(selected.values()), 'versions': preview_versions(connection, selected, targets),
            'preview_hash': hashlib.sha256(encode([sorted(v['id'] for v in selected.values()), digest]).encode()).hexdigest(),
            'can_apply': not any(target['conflicts'] for target in targets)}
