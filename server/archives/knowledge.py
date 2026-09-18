"""Validate character permission receipts without reranking or rewriting saved inputs."""
import hashlib

from server.database import decode, one
from server.errors import require
from server.memory.control_sources import characters, partition_entries, pinned_items
from server.memory.control_state import eligible_version
from server.memory.knowledge import packet, permitted_entries
from server.memory.knowledge_evidence import evidence_key, restored_source


def frozen_entry(entry, links, character_id):
    result = {**entry, 'sources': [restored_source(source, links) for source in entry['sources']]}
    if entry.get('character_id'):
        result['character_id'] = character_id
    return result


def validate_snapshot(connection, snapshot):
    report = snapshot['knowledge_lens']
    require(report['algorithm'] in {'prospero-character-evidence-v1', 'prospero-character-evidence-v2'}, 'Unsupported character evidence format.')
    references = report['algorithm'] == 'prospero-character-evidence-v2'
    character_id = snapshot.get('knowledge_character_id')
    require(bool(character_id) == bool(report.get('character_id')), 'Character identity receipt is incomplete.')
    validate_character(connection, snapshot, report)
    row, path = eligible_version(connection, snapshot['memory_controls_version_id'], snapshot['branch']['head_id'])
    require(row and row['id'] == snapshot['memory_controls_version_id'], 'Character evidence belongs to a future boundary.')
    available, unavailable = partition_entries(connection, snapshot['branch'], decode(row['payload'])['entries'], path)
    entries = permitted_entries({'entries': available, 'unavailable_entries': unavailable}, report['subject'], character_id)
    if not references:
        require(not character_id and all('node_id' in source for entry in entries for source in entry['sources']),
                'Legacy character input cannot grant library material.')
    ids = report['selected_ids']
    require(ids and len(ids) == len(set(ids)), 'Character evidence selections are empty or repeated.')
    selected = [entry for entry in entries if entry['id'] in ids]
    require([entry['id'] for entry in selected] == ids, 'Character evidence includes an unpermitted decision.')
    links = {evidence_key(item): item for item in snapshot['source_links']}
    frozen = [frozen_entry(entry, links, report.get('character_id')) for entry in selected]
    context = decode(snapshot['content'])
    require(context == packet(report['subject'], context['direction'], frozen, context['story']['settings'], report.get('character_id'), references), 'Character input contains changed or unpermitted material.')
    validate_receipt(snapshot, report, entries, selected, links)


def validate_character(connection, snapshot, report):
    if snapshot.get('knowledge_character_id'):
        choices = {item['id']: item['name'] for item in characters(pinned_items(connection, snapshot['branch']))}
        require(choices.get(snapshot['knowledge_character_id']) == report['subject'],
                'Character view uses an unavailable identity or changed name.')


def validate_receipt(snapshot, report, entries, selected, links):
    sources = {source['id'] for entry in selected for source in entry['sources']}
    require(report['permitted_decisions'] == len(entries) and report['selected_decisions'] == len(selected)
            and report['source_count'] == len(sources) == len(links) == len(snapshot['source_links']),
            'Character evidence coverage differs from its permissions.')
    require(report['content_sha256'] == hashlib.sha256(snapshot['content'].encode('utf-8')).hexdigest(),
            'Character input differs from its frozen digest.')
    require(not any(snapshot.get(key) for key in ('lore', 'lore_context', 'opportunity_id', 'memory')),
            'A character request contains outside context.')


def validate_knowledge(connection, data):
    for row in data['generations']:
        snapshot = decode(row['snapshot'])
        if snapshot.get('knowledge_lens'):
            version = one(connection, 'SELECT story_id FROM memory_control_versions WHERE id=?',
                          (snapshot['memory_controls_version_id'],))
            require(version['story_id'] == snapshot['branch']['story_id'], 'Character evidence crosses Stories.')
            validate_snapshot(connection, snapshot)
