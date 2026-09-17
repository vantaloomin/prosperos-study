"""Independent reviews of proposed prose without inserting it into Story history."""
from server.agent_switches import agent_enabled
from server.branches import path_nodes
from server.database import encode, one
from server.errors import require
from server.lore.scene import planned_sources
from server.scenes.chance import chance_sources
from server.scenes.context import draft_view, stale_plan
from server.scenes.drafts import coverage_passes
from server.scenes.state import reviewed_state, run_record, selected_result
from server.stories import check_revision
from server.workflow.catalog import ROLE_MAP
from server.workflow.context import job_snapshot, message_source


def review_target(connection, branch_id, body):
    run = run_record(connection, body.scene_id)
    require(run["branch_id"] == branch_id, "This scene belongs to a different branch.", 409)
    check_revision(run, body.scene_revision)
    require(not stale_plan(connection, run), "The Story changed. Preserve these reports and start a new plan.", 409)
    draft = draft_view(connection, run)
    require(bool(run["state"]["gate_a"]) and draft and draft["complete"], "Approve a plan and complete its selected draft first.", 409)
    require(coverage_passes(selected_result(connection, run, "scene-coverage")) or "scene-coverage" in run["snapshot"].get("disabled_steps", []),
            "Choose a complete beat-coverage assessment before independent scene review.", 409)
    return run, draft


def draft_source(run, draft):
    selected = run["state"]["selections"]
    source_id = f"scene-draft:{run['id']}:{selected['scene-draft']}:{selected.get('scene-dialogue', 'whole')}"
    return {"id": source_id, "kind": "draft", "title": "Proposed scene prose · not accepted Story text", "text": draft["text"]}


def scoped_scene_sources(connection, role, run, draft):
    nodes = path_nodes(connection, run["snapshot"]["branch"]["head_id"])
    prior = [node for node in nodes if node["role"] != "ooc"]
    sources = [draft_source(run, draft)]
    if role["scope"] == "blind":
        return sources + [message_source(node, "previous") for node in prior[-2:]]
    sources.extend(message_source(node, "previous") for node in prior)
    sources.extend(source for source in run["snapshot"]["sources"] if source["kind"] == "reference")
    if role["scope"] == "rules":
        sources.extend(chance_sources(run))
        sources.extend(message_source(node, "guidance") for node in nodes if node["role"] == "ooc")
        sources.append({"id": "story:constraints", "kind": "constraints", "title": "Frozen Story constraints",
                        "text": encode(run["snapshot"]["story_context"])})
        sources.append({"id": "scene:approved-plan", "kind": "plan", "title": "Approved direction · proposed events, not canon",
                        "text": encode(selected_result(connection, run, "scene-beats"))})
    return planned_sources(run, sources)


def scene_review_snapshot(connection, branch_id, body):
    run, draft = review_target(connection, branch_id, body)
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    keys = [step.key for step in body.steps]
    require(len(keys) == len(set(keys)) and set(keys) <= set(ROLE_MAP), "Choose each supported review step once.")
    jobs = []
    for step in body.steps:
        if not agent_enabled(connection, step.key, story) or step.key in run["snapshot"].get("disabled_steps", []):
            continue
        role = ROLE_MAP[step.key]
        context = {"task": "Review only the proposed draft. Its events and details are not accepted Story facts.",
                   "role": role["name"], "scope": role["scope"],
                   "sources": scoped_scene_sources(connection, role, run, draft)}
        jobs.extend(job_snapshot(connection, story, step, context))
    require(bool(jobs), "All selected reviewers are disabled. Enable a reviewer before requesting a review.", 409)
    return {"branch": branch, "story_revision": story["revision"], "from_node_id": None, "through_node_id": None,
            "draft_messages": 1, "scene": {"id": run["id"], "title": run["title"], "revision": run["revision"], "state": reviewed_state(run["state"])},
            "jobs": jobs}


def scene_review_current(connection, snapshot):
    target = snapshot.get("scene")
    if not target:
        return None
    run = run_record(connection, target["id"])
    return reviewed_state(run["state"]) == reviewed_state(target["state"]) and not stale_plan(connection, run)
