"""Freeze permitted paths before recipe jobs are composed; sibling prose is absent."""
from server.branches import path_nodes
from server.continuity import continuity_sources, continuity_view
from server.database import decode, encode, one
from server.errors import require
from server.lore.placement import placed_sources
from server.lore.runtime import current_lore
from server.manifests import manifest_view
from server.mechanics.config import read_settings
from server.memory.control_packet import decision_packet
from server.memory.control_state import control_view
from server.memory.plan_state import plan_head
from server.memory.settings import memory_settings
from server.memory.summary_recall import reviewed_aids
from server.scenes.author_text import selected_draft
from server.scenes.state import run_record, selected_result
from server.workflow.context import message_source, reference_sources


def source_boundary(connection, branch, target):
    ref = target['ref']
    if ref['kind'] == 'scene-block':
        branch = run_record(connection, ref['scene_id'])['snapshot']['branch']
    elif ref['kind'] == 'candidate':
        row = one(connection, 'SELECT g.snapshot FROM generations g JOIN candidates c ON c.generation_id=g.id WHERE c.id=?', (ref['candidate_id'],))
        branch = decode(row['snapshot'])['branch']
    nodes = path_nodes(connection, branch['head_id'])
    if ref['kind'] == 'passage':
        index = next((index for index, node in enumerate(nodes) if node['id'] == ref['node_id']), None)
        require(index is not None, 'Choose a passage visible in the selected telling for this recipe.', 409)
        selected = nodes[index]
        return nodes[:index], {**branch, 'head_id': selected['id'], 'manifest_id': selected['manifest_id']}
    return nodes, branch


def source_bundle(connection, branch, story, target):
    prior, boundary = source_boundary(connection, branch, target)
    prose = [node for node in prior if node['role'] != 'ooc']
    sources = [message_source(node, 'previous') for node in prose]
    sources.extend(reference_sources(connection, boundary['manifest_id']))
    sources.extend(continuity_sources(continuity_view(connection, boundary['head_id'], plan_head(connection, branch['id']))))
    sources.extend(message_source(node, 'guidance') for node in prior if node['role'] == 'ooc')
    settings = decode(story['settings'])
    constraints = {key: settings[key] for key in ('genre', 'tone', 'pov', 'tense', 'persona', 'player_agency',
                   'rules', 'experience', 'response_length') if key in settings}
    sources.append({'id': 'story:constraints', 'kind': 'constraints', 'title': 'Story constraints', 'text': encode(constraints)})
    if story['premise']:
        sources.append({'id': 'story:brief', 'kind': 'guidance', 'title': 'Author Story brief', 'text': story['premise']})
    _, lore = current_lore(connection, boundary, read_settings(story).enabled, prior)
    policy = memory_settings(settings.get('memory'))
    return {'boundary': boundary, 'informed': placed_sources(sources, lore),
            'blind': [message_source(node, 'previous') for node in prose[-2:]],
            'author_memory': decision_packet(control_view(connection, boundary)),
            'assets': manifest_view(connection, boundary['manifest_id']),
            'memory_policy': policy.model_dump(), 'summary_aids': reviewed_aids(connection, boundary, policy),
            'scene': scene_source(connection, target)}


def scene_source(connection, target):
    ref = target['ref']
    if ref['kind'] != 'scene-block':
        return None
    run = run_record(connection, ref['scene_id'])
    draft = selected_draft(connection, run)
    require(run['state']['gate_a'] and draft and draft['complete'], 'Recipe scene work needs an approved plan and complete selected draft.', 409)
    return {'id': run['id'], 'revision': run['revision'], 'beats': selected_result(connection, run, 'scene-beats'),
            'blocks': draft['blocks'], 'block_id': ref['item_id']}
