"""Prepare under a read snapshot; validate immutable dependencies before recording."""
from dataclasses import dataclass

from server.agent_switches import agent_enabled
from server.assessment.context import assessment_needed
from server.background.storage import state_id
from server.context_contract import guard_reviewed_context
from server.database import many, one
from server.errors import require
from server.generation_context import generation_snapshot, selected_profiles
from server.mechanics.config import read_settings
from server.memory.control_state import control_head
from server.memory.summary_recall import summary_dependencies
from server.profiles import resolve_profile
from server.prompts import prompt_snapshot


def assessment_dependencies(connection, story, writer, body, existing, boundary):
    enabled = agent_enabled(connection, 'beat-assessment', story)
    needed = enabled and assessment_needed(story, writer, body)
    if not needed or existing or boundary:
        return {'needed': needed, 'existing': existing}
    settings = read_settings(story)
    tables = {row['id']: row['version_id'] for row in many(connection, 'SELECT id,version_id FROM roll_tables ORDER BY id')}
    tables.update(settings.table_versions)
    return {'needed': True, 'tables': tables, 'prompt': prompt_snapshot(connection, 'beat-assessment', story)['id'],
            'profiles': [resolve_profile(connection, story, 'beat-assessment', item)['id']
                         for item in (body.assessment_profile_ids or [None])]}


def preparation_identity(connection, writer, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (writer['branch']['id'],))
    story = one(connection, 'SELECT id,revision,title,premise,settings,manifest_id FROM stories WHERE id=?',
                (branch['story_id'],))
    existing = many(connection, 'SELECT id,generation_id,stopped FROM assessment_runs WHERE branch_id=? AND head_key=?',
                    (branch['id'], branch['head_id'] or ''))
    opportunities = many(connection, 'SELECT id FROM mechanic_opportunities WHERE branch_id=? AND head_key=?',
                         (branch['id'], branch['head_id'] or ''))
    return {'branch': branch, 'story': story, 'memory_controls': control_head(connection, branch['id']), 'summary_versions': summary_dependencies(connection, story),
            'profiles': [profile['id'] for profile in selected_profiles(connection, story, body.profile_ids)],
            'prompt': prompt_snapshot(connection, 'writer', story)['id'],
            'background': state_id(connection, branch['id']), 'opportunities': opportunities,
            'assessment': assessment_dependencies(connection, story, writer, body, existing, opportunities)}


@dataclass
class PreparedWriter:
    snapshot: dict
    profiles: list
    identity: dict

    def validate(self, connection, body):
        require(self.identity == preparation_identity(connection, self.snapshot, body),
                'The writing inputs changed while context was being assembled. Review the current inputs and '
                'try again. No model request was started.', 409)


def prepare_writer(connection, branch_id, body):
    writer, profiles = generation_snapshot(connection, branch_id, body)
    guard_reviewed_context(connection, writer, profiles, body)
    return PreparedWriter(writer, profiles, preparation_identity(connection, writer, body))
