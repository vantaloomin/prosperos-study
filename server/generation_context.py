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
from server.memory.control_packet import decision_packet
from server.memory.control_state import control_view
from server.memory.index import connection_index
from server.memory.knowledge_writer import knowledge_snapshot
from server.memory.packet import assemble_memory
from server.memory.plan_state import plan_head
from server.memory.settings import memory_settings
from server.memory.summary_excerpt import summary_links
from server.memory.summary_recall import reviewed_aids
from server.memory.writer_recall import freeze_recall
from server.profiles import resolve_profile
from server.prompt_sections import compose, sections_for
from server.prompts import prompt_snapshot
from server.providers.capabilities import input_capacity
from server.stories import check_revision
from server.writing.context import references, request_guidance, writer_profiles


def generation_snapshot(connection, branch_id, body, *, validate_budget=True):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    check_revision(branch, body.expected_revision)
    guidance = request_guidance(connection, story, body)
    profiles = selected_profiles(connection, story, writer_profiles(body.profile_ids, guidance))
    if body.knowledge_subject or body.knowledge_character_id:
        return knowledge_snapshot(connection, branch, story, body, profiles, guidance)
    context = {"story": {"title": story["title"], "premise": story["premise"], "settings": decode(story["settings"])},
               "history": path_nodes(connection, branch["head_id"]),
               "library": manifest_view(connection, branch["manifest_id"]), "direction": body.direction}
    if guidance:
        context['writing_guidance'] = guidance
    context['continuity'] = continuity_view(connection, branch['head_id'], plan_head(connection, branch['id']))
    controls = control_view(connection, branch)
    decisions = decision_packet(controls)
    if decisions:
        context['author_memory'] = decisions
    background = frozen_background(connection, branch_id)
    if 'private_background' in background:
        context['private_background'] = background['private_background']
    canon_assets = context["library"]
    context["library"] = [narrative_asset(item) for item in context["library"] if item["enabled"]]
    opportunity = prepared_context(connection, branch, story, body.use_prepared_beat)
    lore_context, lore = current_lore(connection, branch, read_settings(story).enabled, context['history'])
    lore = selected_for_writer(lore, opportunity)
    context["story"]["settings"].pop("randomness", None)
    if opportunity:
        context["prepared_beat"] = opportunity["snapshot"]["writer"]
    prompt = prompt_snapshot(connection, "writer", story)
    sections = sections_for(connection, 'writer', story, branch['manifest_id'])
    instructions = compose(prompt, sections)
    memory_policy = memory_settings(context['story']['settings'].get('memory'))
    aids = reviewed_aids(connection, branch, memory_policy)
    with connection_index(connection, memory_policy.mode == 'long'):
        prepared, memory = assemble_memory(writer_context(context, lore), instructions, profiles, canon_assets=canon_assets, summary_aids=aids)
    content = encode(prepared)
    estimated = math.ceil(len((instructions + content).encode("utf-8")) / 3)
    if validate_budget:
        validate_writer_budget(profiles, estimated, memory)
    return {"branch": branch, "story_revision": story["revision"], "prompt": prompt, 'prompt_sections': sections,
            **({'writing_versions': references(guidance), 'writing_guidance': guidance} if guidance else {}),
            "continuity_version_id": plan_head(connection, branch_id),
            "memory_controls_version_id": controls["version_id"],
            'lore_context': lore_context, 'lore': lore,
            'background_state_id': background['background_state_id'],
            "opportunity_id": opportunity["id"] if opportunity else None,
            "content": content, "estimated_input_tokens": estimated,
            "coverage": memory['coverage'] if memory else {
                "messages": len(context["history"]), "complete_path": True},
            **({'memory': memory} if memory else {}),
            **({'writer_recall': freeze_recall(connection, branch, context, aids if memory_policy.summary_recall else {})}
               if memory_policy.mode == 'long' and memory_policy.writer_recall else {}),
            **({'summary_links': summary_links(prepared)} if prepared.get('reviewed_summaries') else {})}, profiles


def validate_writer_budget(profiles, estimated, memory=None):
    margin = memory['overhead_margin'] if memory else 0
    for profile in profiles:
        capacity = input_capacity(profile["config"])
        if memory:
            require(estimated + margin <= capacity,
                    f"Required story context needs an estimated {estimated:,} tokens plus {margin:,} "
                    f"for overhead, exceeding {profile['name']}'s allowance. Reduce required guidance "
                    "or Canon, reserve less output, or choose a larger context. Original prose is preserved.", 409)
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
