"""Prepare under a read snapshot; validate immutable dependencies before recording."""
from dataclasses import dataclass
from time import perf_counter

from server.background.storage import state_id
from server.cleanup.settings import frozen_settings
from server.cleanup.settings import settings as cleanup_settings
from server.context_contract import guard_reviewed_context
from server.database import many, one
from server.errors import require
from server.generation_context import generation_snapshot, selected_profiles
from server.mechanics.storage import pending_opportunity
from server.memory.control_state import control_head
from server.memory.summary_recall import summary_dependencies
from server.prompt_sections import sections_for
from server.prompts import prompt_snapshot
from server.request_timing import RECEIVED
from server.writing.context import request_guidance, writer_profiles


def preparation_identity(connection, writer, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (writer['branch']['id'],))
    story = one(connection, 'SELECT id,revision,title,premise,settings,manifest_id FROM stories WHERE id=?',
                (branch['story_id'],))
    existing = many(connection, "SELECT id,generation_id,stopped FROM assessment_runs WHERE branch_id=? AND head_key=? "
                    "AND COALESCE(json_extract(snapshot,'$.purpose'),'') != 'post-acceptance'",
                    (branch['id'], branch['head_id'] or ''))
    opportunities = many(connection, "SELECT o.id FROM mechanic_opportunities o LEFT JOIN assessment_runs a "
                         "ON a.id=json_extract(o.snapshot,'$.assessment_id') WHERE o.branch_id=? AND o.head_key=? "
                         "AND (COALESCE(json_extract(a.snapshot,'$.purpose'),'') != 'post-acceptance' OR o.id=?)",
                         (branch['id'], branch['head_id'] or '', writer.get('opportunity_id')))
    selected = pending_opportunity(connection, branch, story) if writer.get('opportunity_id') else None
    guidance = request_guidance(connection, story, body)
    return {'branch': branch, 'story': story, 'memory_controls': control_head(connection, branch['id']), 'summary_versions': summary_dependencies(connection, story),
            'cleanup': cleanup_settings(connection, branch['id']),
            'profiles': [profile['id'] for profile in selected_profiles(connection, story, writer_profiles(body.profile_ids, guidance))],
            **({'writing_guidance': guidance} if guidance else {}),
            'prompt': prompt_snapshot(connection, 'writer', story)['id'],
            'prompt_sections': sections_for(connection, 'writer', story, branch['manifest_id']),
            'background': state_id(connection, branch['id']), 'opportunities': opportunities,
            'assessment': existing, 'selected_opportunity': selected['id'] if selected else None}


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
    started = perf_counter()
    writer, profiles = generation_snapshot(connection, branch_id, body)
    guard_reviewed_context(connection, writer, profiles, body)
    cleanup = frozen_settings(connection, branch_id, body.cleanup_choices)
    if cleanup:
        writer['cleanup'] = cleanup
    identity = preparation_identity(connection, writer, body)
    writer['timings'] = {'preparation_seconds': perf_counter() - started}
    if RECEIVED.get():
        writer['timings']['request_received_at'] = RECEIVED.get()
    return PreparedWriter(writer, profiles, identity)
