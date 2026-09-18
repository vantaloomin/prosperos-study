"""Recheck cheap dependencies after stage preparation leaves the read connection."""
from server.database import one
from server.errors import require
from server.profiles import resolve_profile
from server.scenes.context import stale_plan
from server.scenes.prompts import stage_prompt
from server.scenes.state import run_record


def guard_stage(connection, run, body, prepared):
    current = run_record(connection, run['id'])
    require(current == run and not stale_plan(connection, current), 'The scene or Story changed. Preview the stage again.', 409)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (run['snapshot']['branch']['story_id'],))
    profiles = [resolve_profile(connection, story, body.key, value) for value in (body.profile_ids or [None])]
    prompt = stage_prompt(connection, story, run, body.key)
    require([(job['profile'], job['prompt']) for job in prepared['jobs']] == [(profile, prompt) for profile in profiles],
            'Model settings or stage instructions changed. Preview again.', 409)
