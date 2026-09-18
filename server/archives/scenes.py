from server.archives.chance import validate_chance
from server.archives.scene_actors import validate_actors
from server.archives.source_memory import validate_scene_projection
from server.archives.summary_context import validate_scene_bindings, validate_summary_context
from server.database import decode, many, one
from server.errors import require
from server.memory.scoped_aids import validate_frozen_aids
from server.scenes.catalog import DRAFT_KEYS, PLAN_KEYS, SCENE_KEYS
from server.scenes.context import stage_inputs
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.models import SceneState
from server.scenes.output import validate_result
from server.scenes.patch_context import patch_keys
from server.scenes.state import (
    dependency_keys,
    planning_keys,
    planning_selections,
    run_record,
    stage_keys,
    upstream,
)


def selected_jobs(connection, run_id, selections):
    require(set(selections) <= set(SCENE_KEYS), "A scene has an unsupported stage selection.")
    for step, job_id in selections.items():
        job = one(connection, "SELECT * FROM scene_jobs WHERE id=?", (job_id,))
        require(job["run_id"] == run_id and job["step"] == step and job["status"] == "done",
                "A scene selection is not a completed result from its own stage and plan.")


def validate_state(connection, run):
    state = SceneState.model_validate(run["state"]).model_dump()
    allowed = stage_keys(run) + ['scene-triage'] + patch_keys(run) + CONTINUITY_KEYS
    require(set(state["selections"]) <= set(allowed), "A selected stage is disabled for this scene.")
    selected_jobs(connection, run["id"], state["selections"])
    for step, job_id in state["selections"].items():
        require(all(key in state["selections"] for key in dependency_keys(run, step)), "A selected scene stage has missing prerequisites.")
        require(step in PLAN_KEYS or bool(state["gate_a"]), "A draft stage was selected without plan approval.")
        job = one(connection, "SELECT snapshot,result FROM scene_jobs WHERE id=?", (job_id,))
        require(decode(job["snapshot"])["upstream"] == upstream(run, step), "A selected scene result has stale dependencies.")
        if step == "scene-options":
            require(state["option_id"] in {option["id"] for option in decode(job["result"])["options"]}, "A chosen option is missing.")
    require(not state["beat_edit"] or "scene-beats" in state["selections"], "An edited plan has no selected source.")
    validate_gate(run, state)


def validate_gate(run, state):
    gate = state["gate_a"]
    if not gate:
        return
    require(all(key in state["selections"] for key in planning_keys(run)), "An approved plan is incomplete.")
    require(gate["selections"] == planning_selections(run), "The approved planning selections disagree.")
    for key in ("option_id", "beat_edit"):
        require(gate[key] == state[key], "The approved plan and selected results disagree.")
    require(bool(gate["approved_at"]) and isinstance(gate["note"], str), "The plan approval is invalid.")


def validate_decisions(connection, run):
    decisions = many(connection, "SELECT * FROM scene_decisions WHERE run_id=? ORDER BY revision", (run["id"],))
    require([row["revision"] for row in decisions] == list(range(1, run["revision"] + 1)), "A plan's decision journal is incomplete.")
    for row in decisions:
        require(row["kind"] in {"request", "choose", "edit", "approve", 'resolve', 'approve-revision', 'repair-patch', 'accept'}, "A director decision is unsupported.")
        payload = decode(row["payload"])
        ids = payload.get("job_ids", []) + ([payload["job_id"]] if payload.get("job_id") else [])
        for job_id in ids:
            job = one(connection, "SELECT run_id FROM scene_jobs WHERE id=?", (job_id,))
            require(job["run_id"] == run["id"], "A director decision refers to another plan.")
    validate_decision_order(connection, run, decisions)


def validate_decision_order(connection, run, decisions):
    approved = False
    for row in decisions:
        kind, payload = row["kind"], decode(row["payload"])
        if kind == "approve":
            require(not approved, "The plan has duplicate approvals.")
            approved = True
            continue
        step = payload.get("step", 'scene-triage' if kind in {'resolve', 'approve-revision', 'repair-patch', 'accept'} else "scene-beats")
        if kind == "choose":
            step = one(connection, "SELECT step FROM scene_jobs WHERE id=?", (payload["job_id"],))["step"]
        require((step in PLAN_KEYS) != approved, "A scene decision crosses the plan-approval boundary.")
    require(approved == bool(run["state"]["gate_a"]), "The plan approval and decision journal disagree.")


def validate_scenes(connection, document):
    for row in document["data"]["scene_jobs"]:
        snapshot = decode(row["snapshot"])
        require(row["step"] in SCENE_KEYS and snapshot["step"] == row["step"], "A scene job has an unsupported stage.")
        selected_jobs(connection, row["run_id"], snapshot["upstream"]["selections"])
        origin = decode(one(connection, 'SELECT snapshot FROM scene_runs WHERE id=?', (row['run_id'],))['snapshot'])
        require(decode(snapshot['content']).get('author_memory') == origin.get('author_memory'),
                'A scene stage changed its frozen author decisions.')
        validate_actors(connection, row, snapshot, origin)
        validate_summary_context(connection, snapshot, origin['branch'], origin.get('memory_policy', {}))
        if snapshot.get("source_memory") and row["step"] in PLAN_KEYS + DRAFT_KEYS:
            validate_scene_memory(connection, row, snapshot)
        if row["status"] == "done":
            validate_result(row["step"], decode(row["result"]), snapshot["content"])
    for row in document["data"]["scene_runs"]:
        run = run_record(connection, row["id"])
        validate_frozen_aids(run['snapshot']['sources'], run['snapshot'].get('summary_aids', {}))
        validate_scene_bindings(connection, run['snapshot'])
        validate_state(connection, run)
        validate_decisions(connection, run)
        validate_chance(connection, run)


def validate_scene_memory(connection, row, snapshot):
    origin = run_record(connection, row['run_id'])
    frozen = {**origin, 'state': SceneState.model_validate(snapshot['upstream']).model_dump()}
    sources = stage_inputs(connection, frozen, row['step'])['sources']
    # Redrafting can retain an earlier coverage report beyond upstream selections.
    # Preserve those recorded non-source inputs; validate the complete source projection.
    expected = {**decode(snapshot['content']), 'sources': sources}
    validate_scene_projection(connection, origin['snapshot'], expected, snapshot)
