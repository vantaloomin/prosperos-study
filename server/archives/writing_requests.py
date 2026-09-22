"""Verify frozen writing instructions against their immutable source versions."""
from copy import deepcopy

from server.archives.identities import SourceIdentities, records
from server.archives.writing_legacy import resolved_legacy
from server.database import decode
from server.errors import require
from server.prompts import ALL_PROMPT_LABELS
from server.writing.resolution import GUIDANCE_NOTICE, resolved_recipe
from server.writing.resources import version


def snapshots(data):
    from server.archives.format import JSON_FIELDS
    for table, fields in JSON_FIELDS.items():
        if 'snapshot' not in fields or table == 'recipe_runs':
            continue
        for row in data[table]:
            snapshot = decode(row['snapshot'])
            yield snapshot
            if snapshot.get('writer_snapshot'):
                yield snapshot['writer_snapshot']


def validate_requests(connection, data):
    identities = SourceIdentities(connection, records(data))
    for snapshot in snapshots(data):
        content = decode(snapshot['content']) if snapshot.get('content') else {}
        guidance = snapshot.get('writing_guidance')
        require(content.get('writing_guidance') == guidance,
                'Saved writing guidance differs from the frozen provider input.')
        if guidance is None:
            require(not snapshot.get('writing_versions'), 'Writing references lack their frozen guidance.')
            continue
        validate_guidance(connection, snapshot, guidance, identities)


def validate_guidance(connection, snapshot, guidance, identities):
    fields = {'version', 'style', 'style_source', 'recipe', 'resolved_recipe', 'guidance'}
    if guidance['version'] == 2:
        fields.update({'variables', 'disabled_baseline'})
    require(guidance['version'] in {1, 2} and set(guidance) == fields,
        'Unsupported saved writing guidance.')
    require(guidance['guidance'] == GUIDANCE_NOTICE and guidance['style_source'] in {'request', 'recipe', 'story'},
            'Saved writing guidance changed its authority boundary.')
    references = snapshot['writing_versions']
    selected = [guidance[key] for key in ('style', 'recipe') if guidance[key]]
    require(len(selected) == len(references) == len(set(references)), 'Writing version references are incomplete.')
    for kind in ('style', 'recipe'):
        frozen = guidance[kind]
        if frozen:
            live_ids = [identity for identity in references if identities.matches(identity, frozen['id'])]
            require(len(live_ids) == 1, 'Frozen writing identity is missing or ambiguous.')
            validate_version(version(connection, live_ids[0], kind), frozen, identities)
    validate_composition(guidance)
    if guidance['style_source'] == 'recipe':
        require(guidance['recipe'], 'A recipe style choice lacks its recipe.')
        selected_style = guidance['style']['id'] if guidance['style'] else 'none'
        require(guidance['recipe']['content']['style'] == selected_style,
                'The selected style differs from the frozen recipe choice.')


def validate_composition(guidance):
    if guidance['version'] == 1:
        expected = resolved_legacy(guidance)
    else:
        disabled = guidance['disabled_baseline']
        require(isinstance(disabled, list) and disabled == sorted(set(disabled)) and set(disabled) <= set(ALL_PROMPT_LABELS),
                'Saved writing task switches are invalid.')
        expected = resolved_recipe(guidance['recipe'], guidance['variables'], set(disabled))
    require(guidance['resolved_recipe'] == expected,
            'Saved recipe instructions or variables differ from the frozen recipe.')


def validate_version(live, frozen, identities):
    expected = {key: live[key] for key in ('id', 'asset_id', 'number', 'name', 'description', 'content')}
    require(set(frozen) == set(expected), 'Frozen writing version has an incomplete schema.')
    candidate = deepcopy(frozen)
    for key in ('id', 'asset_id'):
        require(identities.matches(live[key], frozen[key]), 'Frozen writing version belongs to another resource.')
        candidate[key] = live[key]
    if live['kind'] == 'recipe':
        remap_recipe(candidate['content'], live['content'], identities)
    require(candidate == expected, 'Frozen writing guidance differs from its immutable version.')


def match_reference(candidate, live, key, identities):
    require(identities.matches(live[key], candidate[key]), 'A saved recipe dependency changed identity.')
    candidate[key] = live[key]


def remap_recipe(candidate, live, identities):
    match_reference(candidate, live, 'style', identities)
    require(len(candidate['steps']) == len(live['steps']), 'A saved recipe changed its tasks.')
    for frozen_step, live_step in zip(candidate['steps'], live['steps'], strict=True):
        match_reference(frozen_step, live_step, 'profile_id', identities)
    frozen_tables = (candidate.get('randomness') or {}).get('table_versions', {})
    live_tables = (live.get('randomness') or {}).get('table_versions', {})
    require(set(frozen_tables) == set(live_tables), 'A saved recipe changed its table dependencies.')
    for key in live_tables:
        match_reference(frozen_tables, live_tables, key, identities)
