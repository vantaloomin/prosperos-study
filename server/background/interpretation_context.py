import json

from pydantic import ValidationError

from server.background.engine import AUTHORITY
from server.background.interpretation_models import InterpretationOutput
from server.background.storage import state_id
from server.background.targets import private_targets
from server.branches import path_nodes
from server.continuity import continuity_sources, continuity_view
from server.database import decode, one
from server.errors import DomainError, require
from server.memory.plan_state import plan_head
from server.scenes.context import story_context
from server.stories import check_revision
from server.workflow.context import job_snapshot, message_source, reference_sources, snapshot_hash


def interpretation_snapshot(connection, branch_id, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    setup_id = state_id(connection, branch_id)
    require(setup_id is not None, 'Prepare the background cues first.', 409)
    setup = decode(one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (setup_id,))['snapshot'])
    targets = private_targets(setup)
    require(any(targets.values()), 'No enabled background targets remain. Enable a prepared feature or prepare another path.', 409)
    sources = [message_source(node, 'accepted') for node in path_nodes(connection, branch['head_id'])]
    sources.extend(reference_sources(connection, branch['manifest_id']))
    sources.extend(continuity_sources(continuity_view(connection, branch['head_id'], plan_head(connection, branch['id']))))
    context = {'authority': AUTHORITY, 'story': story_context(story), 'targets': targets, 'sources': sources,
               'chronology': {'origin': setup['recipe']['origin'], 'day': setup['day']}, 'direction': body.direction}
    jobs = job_snapshot(connection, story, body, context)
    return {'branch': branch, 'story_revision': story['revision'], 'background_state_id': setup_id,
            'content': jobs[0]['content'], 'jobs': jobs}


def preview_view(snapshot):
    targets = decode(snapshot['content'])['targets']
    return {'preview_hash': snapshot_hash(snapshot), 'request_count': len(snapshot['jobs']),
            'target_counts': {key: len(value) for key, value in targets.items()}, 'jobs': [
                {'profile_name': job['profile']['name'], 'model': job['profile']['config']['model'],
                 'prompt_version': job['prompt']['number'], 'estimated_input_tokens': job['estimated_input_tokens']}
                for job in snapshot['jobs']]}


def parse_interpretation(output, snapshot):
    try:
        result = InterpretationOutput.model_validate(json.loads(output)).model_dump()
    except (ValueError, ValidationError) as error:
        raise DomainError('The private background did not match its required structure. The original output is preserved; retry is explicit.', 502) from error
    context = decode(snapshot['content'])
    sources = {item['id']: item['text'] for item in context['sources']}
    for kind in ('drives', 'hooks'):
        targets = {item['id'] for item in context['targets'][kind]}
        require(len(result[kind]) == len(targets) and {item['target_id'] for item in result[kind]} == targets,
                'Private interpretation must cover exactly the enabled seeded targets without adding or dropping any.', 502)
        for item in result[kind]:
            for basis in item['basis']:
                require(basis['source_id'] in sources and basis['quote'] in sources[basis['source_id']],
                        'Private interpretation evidence must quote its supplied sources exactly.', 502)
    return result
