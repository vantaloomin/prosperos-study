import hashlib
import math

from server.agent_switches import agent_enabled
from server.branches import path_nodes
from server.character_content import narrative_asset
from server.continuity import continuity_sources, continuity_view
from server.database import decode, encode, one
from server.errors import require
from server.lore.placement import placed_sources
from server.lore.runtime import current_lore
from server.manifests import manifest_view
from server.mechanics.config import read_settings
from server.profiles import resolve_profile
from server.prompts import prompt_snapshot
from server.stories import check_revision
from server.workflow.catalog import ROLE_MAP


def selected_path(nodes, body):
    positions = {node["id"]: index for index, node in enumerate(nodes)}
    require(bool(nodes), "Add some story text before requesting a review.", 409)
    requested = [value for value in [body.from_node_id, body.through_node_id] if value]
    require(all(value in positions for value in requested), "Review passages must belong to this path.", 409)
    start = positions[body.from_node_id] if body.from_node_id else 0
    end = positions[body.through_node_id] if body.through_node_id else len(nodes) - 1
    require(start <= end, "The review must start before it ends.")
    return nodes[:start], nodes[start:end + 1], nodes[:end + 1]


def message_source(node, kind):
    return {"id": f"message:{node['id']}", "kind": kind, "title": f"{node['role']} contribution", "text": node["text"]}


def reference_sources(connection, manifest_id):
    return [{"id": f"asset:{item['version_id']}", "kind": "reference", "title": item["version"]["name"],
             "text": encode(narrative_asset(item)["version"]["content"])}
            for item in manifest_view(connection, manifest_id) if item["enabled"]]


def scoped_sources(connection, role, story, prior, draft, prefix):
    sources = [message_source(node, "draft") for node in draft if node["role"] != "ooc"]
    require(bool(sources), "Choose a passage with story prose; OOC notes are not a scene.")
    prior_prose = [node for node in prior if node["role"] != "ooc"]
    if role["scope"] == "blind":
        return sources + [message_source(node, "previous") for node in prior_prose[-2:]]
    sources.extend(message_source(node, "previous") for node in prior_prose)
    sources.extend(reference_sources(connection, prefix[-1]["manifest_id"]))
    sources.extend(continuity_sources(continuity_view(connection, prefix[-1]['id'])))
    if role["scope"] == "rules":
        sources.extend(message_source(node, "guidance") for node in prefix if node["role"] == "ooc")
        settings = decode(story["settings"])
        constraints = {key: settings[key] for key in ["genre", "tone", "pov", "tense", "persona", "player_agency", "rules", 'experience', 'response_length'] if key in settings}
        sources.append({"id": "story:constraints", "kind": "constraints", "title": "Story constraints", "text": encode(constraints)})
    origin = {'head_id': prefix[-1]['id'], 'manifest_id': prefix[-1]['manifest_id']}
    _, lore = current_lore(connection, origin, read_settings(story).enabled, prefix)
    return placed_sources(sources, lore)


def job_snapshot(connection, story, selection, context, *, validate_budget=True):
    require(len(selection.profile_ids) == len(set(selection.profile_ids)), "Select each comparison profile once.")
    profiles = [resolve_profile(connection, story, selection.key, value) for value in (selection.profile_ids or [None])]
    prompt = prompt_snapshot(connection, selection.key, story)
    content = encode(context)
    estimate = math.ceil(len((prompt["template"] + content).encode("utf-8")) / 3)
    if validate_budget:
        validate_job_budget(profiles, estimate)
    return [{"step": selection.key, "profile": profile, "prompt": prompt,
             "content": content, "estimated_input_tokens": estimate} for profile in profiles]


def validate_job_budget(profiles, estimate):
    for profile in profiles:
        capacity = profile["config"]["context_tokens"] - profile["config"]["max_output_tokens"]
        require(estimate <= capacity, f"{profile['name']} cannot fit this request's estimated {estimate:,} input tokens. "
                "Choose a narrower passage or a larger context allowance. No sources were silently dropped.", 409)


def review_snapshot(connection, branch_id, body):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    check_revision(branch, body.expected_revision)
    keys = [step.key for step in body.steps]
    require(len(keys) == len(set(keys)) and set(keys) <= set(ROLE_MAP), "Choose each supported review step once.")
    prior, draft, prefix = selected_path(path_nodes(connection, branch["head_id"]), body)
    jobs = []
    for step in body.steps:
        if not agent_enabled(connection, step.key, story):
            continue
        role = ROLE_MAP[step.key]
        sources = scoped_sources(connection, role, story, prior, draft, prefix)
        context = {"task": "Review the draft sources; the other sources are context, not additional draft passages.",
                   "role": role["name"], "scope": role["scope"], "sources": sources}
        jobs.extend(job_snapshot(connection, story, step, context))
    require(bool(jobs), "All selected reviewers are disabled. Enable a reviewer in Settings > Prompts.", 409)
    return {"branch": branch, "story_revision": story["revision"], "from_node_id": draft[0]["id"],
            "through_node_id": draft[-1]["id"], "draft_messages": len(draft), "jobs": jobs}


def snapshot_hash(snapshot):
    return hashlib.sha256(encode(snapshot).encode("utf-8")).hexdigest()


def preview_view(snapshot):
    return {"preview_hash": snapshot_hash(snapshot), "draft_messages": snapshot["draft_messages"], "scene": snapshot.get("scene"),
            "request_count": len(snapshot["jobs"]), "jobs": [
                {"step": job["step"], "name": ROLE_MAP[job["step"]]["name"], "scope": ROLE_MAP[job["step"]]["scope"],
                 "profile_name": job["profile"]["name"], "model": job["profile"]["config"]["model"],
                 "estimated_input_tokens": job["estimated_input_tokens"], "prompt_version": job["prompt"]["number"],
                 "source_count": len(decode(job["content"])["sources"])} for job in snapshot["jobs"]]}
