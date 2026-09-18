"""Bind new Canon receipts to immutable manifests during archive validation."""
import hashlib
from types import SimpleNamespace

from server.archives.summary_context import validate_summary_context
from server.branches import path_nodes
from server.database import decode, encode, one
from server.errors import require
from server.manifests import manifest_view
from server.memory.source_replay import validate_job_projection
from server.memory.summary_excerpt import summary_items
from server.roles import task_context
from server.workflow.catalog import ROLE_MAP
from server.workflow.context import scoped_sources, selected_path


def has_canon(snapshot):
    memory = snapshot.get('source_memory')
    if memory is None:
        return False
    require(isinstance(memory, dict), 'Invalid specialist source memory receipt.')
    return 'canon' in memory


def canon_assets(connection, manifest_id, snapshot):
    if not has_canon(snapshot):
        return None
    return manifest_view(connection, manifest_id)


def validate_scene_projection(connection, origin, expected, snapshot):
    if snapshot.get('role'):
        expected = task_context(snapshot['step'], expected)
    require(not has_canon(snapshot) or origin.get('memory_policy', {}).get('mode') == 'long',
            'Full history cannot carry a selective Canon receipt.')
    assets = canon_assets(connection, origin['branch']['manifest_id'], snapshot)
    validate_job_projection(expected, snapshot, origin.get('summary_aids', {}), assets)
    validate_summary_context(connection, snapshot, origin['branch'], origin.get('memory_policy', {}))


def validate_historical_memory(connection, row, run, job):
    snapshot = decode(job['snapshot'])
    if not has_canon(snapshot) and not snapshot.get('summary_links') and not summary_items(decode(snapshot['content'])):
        return
    origin = snapshot.get('source_context')
    require(isinstance(origin, dict) and snapshot.get('source_context_format') == 'identities-v1'
            and isinstance(run.get('review_settings'), dict),
            'A historical Canon review lacks its frozen permitted sources.')
    require(run['review_settings'].get('memory', {}).get('mode') == 'long',
            'Full history cannot carry a selective Canon review.')
    branch = run['branch']
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    prior, draft, prefix = selected_path(path_nodes(connection, branch['head_id']),
                                        SimpleNamespace(**{key: run[key] for key in ('from_node_id', 'through_node_id')}))
    require(prefix[-1]['story_id'] == branch['story_id'] and row['branch_id'] == branch['id'], 'A Canon review crosses Stories.')
    role = ROLE_MAP[job['step']]
    require(origin.get('scope') == role['scope'] and role['scope'] != 'blind', 'A Canon review changed its permitted role.')
    expected = scoped_sources(connection, role, {**story, 'settings': encode(run['review_settings'])}, prior, draft, prefix, run.get('continuity_version_id'))
    assets = manifest_view(connection, prefix[-1]['manifest_id'])
    frozen_versions = validate_reference_links(snapshot, assets)
    sources = restore_source_bytes(origin['sources'], expected, frozen_versions, snapshot['source_links'])
    validate_job_projection({**origin, 'sources': sources}, snapshot, canon_assets=assets)
    validate_summary_context(connection, snapshot, {**branch, 'head_id': prefix[-1]['id']}, run['review_settings'].get('memory', {}))


def validate_reference_links(snapshot, assets):
    links = [link for link in snapshot.get('source_links', []) if 'version_id' in link]
    enabled = [item for item in assets if item['enabled']]
    require(len(links) == len(enabled), 'A Canon review has incomplete reference links.')
    sources = [source for source in snapshot['source_context']['sources'] if source['kind'] == 'reference']
    require(len(sources) == len(links), 'A Canon review has foreign reference links.')
    for link, asset, source in zip(links, enabled, sources, strict=True):
        require(link['asset_id'] == asset['asset_id'] and link['version_id'] == asset['version_id']
                and link['id'] == source['id'] == f"asset:{link['frozen_version_id']}",
                'A Canon review reference belongs to another edition.')
    return {link['version_id']: link['frozen_version_id'] for link in links}


def source_text(source, frozen_versions):
    if source['kind'] != 'reference':
        return source['text']
    content = decode(source['text'])
    if 'lorebook_versions' not in content:
        return source['text']
    content['lorebook_versions'] = [frozen_versions.get(value, value) for value in content['lorebook_versions']]
    return encode(content)


def restore_source_bytes(origins, expected, frozen_versions, links):
    require(len(origins) == len(expected), 'A Canon review changed its historical source count.')
    nodes = {item['id']: item['node_id'] for item in links if 'node_id' in item}
    require(len(nodes) == sum(source['id'].startswith('message:') for source in expected),
            'A Canon review has incomplete message bindings.')
    require(len({item['id'] for item in links}) == len(links), 'A Canon review has duplicate source bindings.')
    sources = []
    for origin, live in zip(origins, expected, strict=True):
        text = source_text(live, frozen_versions)
        require('text' not in origin and all(origin[key] == live[key] for key in ('kind', 'title'))
                and origin.get('source_text_sha256') == hashlib.sha256(text.encode()).hexdigest(),
                'A Canon review changed its historical permitted sources.')
        if live['id'].startswith('message:'):
            require(nodes.get(origin['id']) == live['id'].removeprefix('message:'),
                    'A Canon review source refers to another message.')
        sources.append({**{key: value for key, value in origin.items() if key != 'source_text_sha256'}, 'text': text})
    return sources
