import math

from server.background.storage import frozen_background
from server.branches import path_nodes
from server.character_content import narrative_asset
from server.continuity import continuity_view
from server.database import decode, encode, one
from server.errors import require
from server.lore.placement import writer_context
from server.lore.runtime import current_lore, selected_for_writer
from server.manifests import manifest_view
from server.mechanics.config import read_settings
from server.mechanics.storage import opportunity_stale, pending_opportunity
from server.profiles import resolve_profile
from server.prompts import prompt_snapshot
from server.stories import check_revision


def generation_snapshot(connection, branch_id, body, *, validate_budget=True):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    check_revision(branch, body.expected_revision)
    profiles = selected_profiles(connection, story, body.profile_ids)
    context = {"story": {"title": story["title"], "premise": story["premise"], "settings": decode(story["settings"])},
               "history": path_nodes(connection, branch["head_id"]),
               "library": manifest_view(connection, branch["manifest_id"]), "direction": body.direction}
    context['continuity'] = continuity_view(connection, branch['head_id'])
    background = frozen_background(connection, branch_id)
    if 'private_background' in background:
        context['private_background'] = background['private_background']
    context["library"] = [narrative_asset(item) for item in context["library"] if item["enabled"]]
    opportunity = prepared_context(connection, branch, story, body.use_prepared_beat)
    lore_context, lore = current_lore(connection, branch, read_settings(story).enabled, context['history'])
    lore = selected_for_writer(lore, opportunity)
    context["story"]["settings"].pop("randomness", None)
    if opportunity:
        context["prepared_beat"] = opportunity["snapshot"]["writer"]
    prompt = prompt_snapshot(connection, "writer", story)
    content = encode(writer_context(context, lore))
    estimated = math.ceil(len((prompt["template"] + content).encode("utf-8")) / 3)
    if validate_budget:
        validate_writer_budget(profiles, estimated)
    return {"branch": branch, "story_revision": story["revision"], "prompt": prompt,
            'lore_context': lore_context, 'lore': lore,
            'background_state_id': background['background_state_id'],
            "opportunity_id": opportunity["id"] if opportunity else None,
            "content": content, "estimated_input_tokens": estimated,
            "coverage": {"messages": len(context["history"]), "complete_path": True}}, profiles


def validate_writer_budget(profiles, estimated):
    for profile in profiles:
        capacity = profile["config"]["context_tokens"] - profile["config"]["max_output_tokens"]
        require(estimated <= capacity,
                f"Full context is estimated at {estimated:,} tokens and exceeds {profile['name']}'s allowance. "
                "Increase its context limit or use another profile. Nothing was silently omitted.", 409)


def prepared_context(connection, branch, story, enabled):
    opportunity = pending_opportunity(connection, branch, story) if enabled else None
    if opportunity:
        require(not opportunity_stale(opportunity, branch, story),
                "The prepared beat predates a story change. Reroll on a new branch, or write without this beat.", 409)
    return opportunity


def selected_profiles(connection, story, ids):
    require(len(ids) == len(set(ids)), "Select each comparison profile once.")
    selected = ids or [None]
    return [resolve_profile(connection, story, "writer", profile_id) for profile_id in selected]
