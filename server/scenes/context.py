from server.background.storage import frozen_background
from server.branches import path_nodes
from server.continuity import continuity_sources, continuity_view
from server.database import decode, encode, one
from server.errors import require
from server.lore.placement import placed_sources
from server.lore.runtime import current_lore
from server.lore.scene import planned_sources
from server.mechanics.config import read_settings
from server.memory.control_packet import decision_packet
from server.memory.control_state import control_view
from server.memory.plan_state import plan_head
from server.memory.settings import memory_settings
from server.memory.source_evidence import carry_evidence, cited_ids
from server.memory.summary_excerpt import aid_items, summary_links
from server.memory.summary_recall import reviewed_aids
from server.scenes.actor_context import actor_jobs, actor_preview
from server.scenes.catalog import DRAFT_KEYS, SCENE_STEPS
from server.scenes.chance import chance_sources, chance_stale, freeze_chance
from server.scenes.continuity_context import continuity_inputs
from server.scenes.drafts import assemble_draft
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.patch_context import patch_inputs
from server.scenes.prompts import stage_prompt
from server.scenes.revision_catalog import REVISION_KEYS
from server.scenes.revision_context import revision_inputs
from server.scenes.state import require_step, selected_result, upstream
from server.scenes.switches import scene_switches
from server.stories import check_revision
from server.workflow.context import job_snapshot, message_source, reference_sources, snapshot_hash


def story_context(story):
    settings = decode(story["settings"])
    keys = ("genre", "tone", "pov", "tense", "persona", "player_agency", "rules", 'experience', 'response_length')
    return {"premise": story["premise"], "constraints": {key: settings[key] for key in keys if key in settings}}


def create_snapshot(connection, branch_id, body):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    context = story_context(story)
    policy = memory_settings(decode(story['settings']).get('memory'))
    controls = control_view(connection, branch)
    history = path_nodes(connection, branch['head_id'])
    sources = [message_source(node, "accepted") for node in history]
    sources.extend(reference_sources(connection, branch["manifest_id"]))
    continuity = continuity_view(connection, branch['head_id'], plan_head(connection, branch['id']))
    sources.extend(continuity_sources(continuity))
    sources.append({"id": "story:context", "kind": "constraints", "title": "Story premise and constraints", "text": encode(context)})
    lore_context, lore = current_lore(connection, branch, read_settings(story).enabled, history)
    sources = placed_sources(sources, lore)
    aids = reviewed_aids(connection, branch, policy)
    bindings = summary_links({'sources': aid_items(sources, aids)}) if policy.summary_context else []
    return {"branch": branch, "story_context": context, "direction": body.direction,
            "continuity_version_id": plan_head(connection, branch_id),
            "memory_policy": policy.model_dump(),
            "memory_controls_version_id": controls["version_id"], "author_memory": decision_packet(controls),
            "summary_aids": aids, **({"summary_aid_links": bindings} if bindings else {}),
            "propose_options": body.propose_options, **scene_switches(connection, story, body.dialogue_split), "sources": sources,
            'continuity': continuity, 'lore_context': lore_context, 'lore': lore,
            **freeze_chance(connection, branch, story), **frozen_background(connection, branch_id)}


def stale_plan(connection, run):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (run["branch_id"],))
    original = run["snapshot"]["branch"]
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    return (any(branch[key] != original[key] for key in ("head_id", "revision", "manifest_id"))
            or story_context(story) != run["snapshot"]["story_context"] or chance_stale(story, run['snapshot']))


def stage_inputs(connection, run, key):
    if key == 'scene-continuity':
        return continuity_inputs(connection, run)
    if key in PATCH_KEYS:
        return patch_inputs(connection, run, key)
    snapshot = run["snapshot"]
    context = {"stage": key, "director_direction": snapshot["direction"],
               "sources": planned_sources(run, [*snapshot["sources"], *chance_sources(run)])}
    if key in {'scene-options', 'scene-beats', 'scene-brief'} and snapshot.get('private_background'):
        context['private_background'] = snapshot['private_background']
    if key == 'scene-beats' and snapshot.get('chance_version'):
        context['chance_boundaries'] = {'enabled': snapshot['settings']['enabled'],
            'schema': 'Each beat may include chance: {completed, waiting_for_player, protected, resolves_event, new_scene, family, attempt, extras}.',
            'rule': 'Mark completed only at a meaningful completed boundary; waiting_for_player stays true for an unresolved choice. Family is narrative-push, encounter, or none. No draws occur while planning. Omitted boundaries are ineligible.'}
    options = selected_result(connection, run, "scene-options")
    if key != "scene-options" and options:
        context["chosen_option"] = next(item for item in options["options"] if item["id"] == run["state"]["option_id"])
    if key == "scene-brief" or key in DRAFT_KEYS:
        context["proposed_beats"] = selected_result(connection, run, "scene-beats")
    if key in DRAFT_KEYS:
        context.update(drafting_inputs(connection, run, key))
        context["sources"] = brief_evidence(connection, run, context)
        if snapshot.get("disabled_steps"):
            context["skipped_stages"] = snapshot["disabled_steps"]
            context["direction_rule"] = "Use director_direction and sources directly where a planning stage was skipped; do not invent an approved plan."
    return context


def brief_evidence(connection, run, context):
    job_id = run['state']['selections'].get('scene-brief')
    if not job_id:
        return context['sources']
    job = one(connection, 'SELECT snapshot FROM scene_jobs WHERE id=?', (job_id,))
    snapshot = decode(job['snapshot'])
    if not snapshot.get('source_memory'):
        return context['sources']
    return carry_evidence(context['sources'], cited_ids(context), decode(snapshot['content'])['sources'])


def drafting_inputs(connection, run, key):
    context = {"continuity_brief": selected_result(connection, run, "scene-brief"),
               "dialogue_split": run["snapshot"].get("dialogue_split", False)}
    if run['snapshot'].get('workflow_version', 1) >= 2:
        context.pop('continuity_brief')
        context['continuity'] = run['snapshot'].get('continuity', {})
    coverage = selected_result(connection, run, "scene-coverage")
    if key == "scene-draft" and coverage:
        context["revision_context"] = {"draft": draft_view(connection, run), "coverage": coverage}
        context['revision_context']['triage'] = selected_result(connection, run, 'scene-triage')
        context['revision_context']['director_resolutions'] = run['state'].get('triage_edits', {})
    if key == "scene-dialogue":
        context["skeleton"] = selected_result(connection, run, "scene-draft")
    if key == "scene-coverage":
        context["draft"] = draft_view(connection, run)
        require(context["draft"] and context["draft"]["complete"], "Fill every dialogue slot before coverage review.", 409)
    return context


def draft_view(connection, run):
    draft = selected_result(connection, run, "scene-draft")
    return assemble_draft(draft, selected_result(connection, run, "scene-dialogue")) if draft else None


def stage_snapshot(connection, run, body):
    check_revision(run, body.expected_revision)
    require(not body.dialogue_actors or body.key == 'scene-dialogue', 'Character writers apply to the dialogue stage only.')
    require(not run['state']['accepted'], 'This scene was accepted. Start a new scene for further work.', 409)
    require_step(run, body.key)
    require(not stale_plan(connection, run), "The Story changed since this plan began. Start a new plan from the current path.", 409)
    story = one(connection, "SELECT * FROM stories WHERE id=?", (run["snapshot"]["branch"]["story_id"],))
    context = revision_inputs(connection, run, body) if body.key in REVISION_KEYS else stage_inputs(connection, run, body.key)
    require(body.key in REVISION_KEYS or not (body.review_job_ids or body.item_id), 'Review targets only apply to revision stages.')
    if run['snapshot'].get('author_memory'):
        context['author_memory'] = run['snapshot']['author_memory']
    jobs = actor_jobs(connection, story, run, body, context) if body.dialogue_actors else job_snapshot(
        connection, story, body, context, memory_policy=run['snapshot'].get('memory_policy'), summary_aids=run['snapshot'].get('summary_aids'),
        manifest_id=run['snapshot']['branch']['manifest_id'], summary_bindings=run['snapshot'].get('summary_aid_links'),
        prompt=stage_prompt(connection, story, run, body.key))
    for job in jobs:
        job["upstream"] = upstream(run, body.key)
        if body.key in REVISION_KEYS:
            job.update(review_job_ids=body.review_job_ids, item_id=body.item_id)
    return {"run_id": run["id"], "revision": run["revision"], "jobs": jobs}


def preview_view(snapshot):
    names = {step["key"]: step["name"] for step in SCENE_STEPS}
    return {"preview_hash": snapshot_hash(snapshot), "request_count": sum(len(job.get("dialogue_actors", [])) or 1 for job in snapshot["jobs"]), "jobs": [
        {"step": job["step"], "name": names[job["step"]], "profile_name": job["profile"]["name"],
         "model": job["profile"]["config"]["model"], "estimated_input_tokens": job["estimated_input_tokens"],
         "prompt_version": job["prompt"]["number"], "source_count": len(decode(job["content"])["sources"]),
         "source_memory": job.get("source_memory"), "dialogue_actors": actor_preview(job)}
        for job in snapshot["jobs"]]}
