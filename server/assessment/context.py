import json
import secrets

from pydantic import ValidationError

from server.assessment.models import AssessmentOutput
from server.database import decode
from server.errors import DomainError, require
from server.mechanics.config import configured_tables, read_settings
from server.mechanics.state import node_state
from server.workflow.context import job_snapshot
from server.workflow.models import ReviewStep


def eligible_head(snapshot):
    history = decode(snapshot['content'])['history']
    if not history or history[-1]['role'] == 'ooc':
        return None
    node = history[-1]
    return None if node['metadata'].get('source') == 'manual_edit' else node['id']


def assessment_needed(story, snapshot, body):
    settings = read_settings(story)
    return (settings.enabled and settings.automatic_assessment and body.assess_beat
            and not snapshot['opportunity_id'] and eligible_head(snapshot) is not None)


def assessment_snapshot(connection, story, writer, profiles, body):
    settings = read_settings(story)
    tables = configured_tables(connection, settings)
    settings.table_versions = {key: value['id'] for key, value in tables.items()}
    before = node_state(connection, writer['branch']['head_id'])
    context = assessment_input(writer, before, settings)
    selection = ReviewStep(key='beat-assessment', profile_ids=body.assessment_profile_ids)
    return {'branch': writer['branch'], 'story_revision': story['revision'], 'settings': settings.model_dump(),
            'seed': secrets.token_hex(16), 'tables': tables, 'before': before, 'writer_snapshot': writer, 'writer_profiles': profiles,
            'request': body.model_dump(exclude={'operation_id'}),
            'jobs': job_snapshot(connection, story, selection, context)}


def assessment_input(writer, before, settings):
    context = {'eligible_head_id': eligible_head(writer), 'context': decode(writer['content']),
               'accepted_mechanics': before, 'enabled_optional_tables': settings.enabled_extras,
               'sources': []}
    context['context'].pop('private_background', None)
    return context


def parse_assessment(output, snapshot):
    try:
        result = AssessmentOutput.model_validate(json.loads(output))
    except (ValueError, ValidationError) as error:
        raise DomainError('The beat assessor returned an invalid report. Its output is preserved; retry or continue without chance.', 502) from error
    context = decode(snapshot['content'])
    nodes = {node['id']: node for node in context['context']['history']}
    for evidence in result.evidence:
        node = nodes.get(evidence.node_id)
        require(node and node['role'] != 'ooc' and evidence.quote in node['text'],
                'Beat evidence must quote accepted story text exactly; OOC notes are not completed beats.', 502)
    if result.beat.completed:
        require(result.boundary_node_id == context['eligible_head_id']
                and any(item.node_id == result.boundary_node_id for item in result.evidence),
                'A completed beat needs evidence at the current narrative boundary.', 502)
    require(set(result.beat.extras) <= set(context['enabled_optional_tables']),
            'The assessor requested an optional table that is not enabled.', 502)
    return result.model_dump()
