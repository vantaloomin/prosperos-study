from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.scenes.acceptance import accept_scene
from server.scenes.chance import prepare_chance
from server.scenes.context import (
    create_snapshot,
    draft_view,
    preview_view,
    stage_snapshot,
    stale_plan,
)
from server.scenes.drafts import coverage_passes
from server.scenes.manual_acceptance import manual_material
from server.scenes.models import SceneState
from server.scenes.output import validate_result
from server.scenes.patch_context import patch_view, repair_patch, require_patch_choice
from server.scenes.revision_context import available_reports
from server.scenes.revision_decisions import approve_revision, resolve_item, revision_view
from server.scenes.state import (
    choose_state,
    next_step,
    run_record,
    save_decision,
    selected_result,
    upstream,
)
from server.stories import check_revision
from server.workflow.context import snapshot_hash
from server.workflow.reviews import job_view


class Scenes:
    def __init__(self, database):
        self.database = database

    def create(self, branch_id, body):
        payload = {"branch_id": branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "scene-create", payload)
            if cached is not None:
                return cached
            snapshot = create_snapshot(connection, branch_id, body)
            run_id = identifier()
            connection.execute("INSERT INTO scene_runs (id,branch_id,title,snapshot,state,created_at) VALUES (?,?,?,?,?,?)",
                               (run_id, branch_id, body.title, encode(snapshot), encode(SceneState().model_dump()), now()))
            return remember(connection, body.operation_id, "scene-create", payload, {"id": run_id})

    def list(self, branch_id):
        with self.database.connect() as connection:
            one(connection, "SELECT id FROM branches WHERE id=?", (branch_id,))
            return many(connection, "SELECT id,title,revision,created_at FROM scene_runs WHERE branch_id=? ORDER BY created_at DESC", (branch_id,))

    def detail(self, run_id):
        with self.database.connect() as connection:
            run = run_record(connection, run_id)
            jobs = many(connection, "SELECT * FROM scene_jobs WHERE run_id=? ORDER BY rowid", (run_id,))
            decisions = many(connection, "SELECT * FROM scene_decisions WHERE run_id=? ORDER BY revision", (run_id,))
            views = [{**job_view(job), "current_inputs": decode(job["snapshot"])["upstream"] == upstream(run, job["step"])} for job in jobs]
            coverage = selected_result(connection, run, "scene-coverage")
            return {**run, "jobs": views, "next_step": next_step(run), "draft": draft_view(connection, run),
                    'revision_plan': revision_view(connection, run),
                    'patch': patch_view(connection, run),
                    'continuity_proposal': selected_result(connection, run, 'scene-continuity'),
                    "coverage_passes": coverage_passes(coverage),
                    "manual_acceptance": manual_material(connection, run),
                    "stale": stale_plan(connection, run), "plan": selected_result(connection, run, "scene-beats"),
                    "decisions": [{**row, "payload": decode(row["payload"])} for row in decisions]}

    def preview(self, run_id, body):
        with self.database.connect() as connection:
            return preview_view(stage_snapshot(connection, run_record(connection, run_id), body))

    def reports(self, run_id):
        with self.database.connect() as connection:
            return available_reports(connection, run_record(connection, run_id))

    def start(self, run_id, body):
        payload = {"run_id": run_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "scene-stage", payload)
            if cached is not None:
                return cached
            run = run_record(connection, run_id)
            snapshot = stage_snapshot(connection, run, body)
            require(body.preview_hash == snapshot_hash(snapshot), "The stage inputs changed. Preview again before generating.", 409)
            ids = insert_jobs(connection, run_id, snapshot["jobs"])
            save_decision(connection, run, "request", {"step": body.key, "job_ids": ids}, run["state"])
            return remember(connection, body.operation_id, "scene-stage", payload, {"id": run_id, "job_ids": ids})

    def decide(self, run_id, body, kind):
        payload = {"run_id": run_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, f"scene-{kind}", payload)
            if cached is not None:
                return cached
            run = run_record(connection, run_id)
            check_revision(run, body.expected_revision)
            require(not run['state']['accepted'], 'This scene is accepted. Open its recorded branch or start another scene.', 409)
            require(kind == 'accept' or not stale_plan(connection, run), "The Story changed. Preserve this plan and start a new one on the current path.", 409)
            state = DECISIONS[kind](connection, run, body)
            result = save_decision(connection, run, kind, body.model_dump(), state)
            return remember(connection, body.operation_id, f"scene-{kind}", payload, result)

    def attempts(self, job_id):
        with self.database.connect() as connection:
            rows = many(connection, "SELECT * FROM scene_attempts WHERE job_id=? ORDER BY attempt DESC", (job_id,))
            return [{**row, "result": decode(row["result"]), "usage": decode(row["usage"])} for row in rows]


def insert_jobs(connection, run_id, jobs):
    ids = []
    for snapshot in jobs:
        job_id = identifier()
        connection.execute("INSERT INTO scene_jobs (id,run_id,step,snapshot,status,updated_at) VALUES (?,?,?,?,'queued',?)",
                           (job_id, run_id, snapshot["step"], encode(snapshot), now()))
        ids.append(job_id)
    return ids


def choose(connection, run, body):
    job = one(connection, "SELECT * FROM scene_jobs WHERE id=?", (body.job_id,))
    require(job["run_id"] == run["id"] and job["status"] == "done", "Choose a completed result from this plan.", 409)
    require_patch_choice(connection, run, job['step'])
    return choose_state(run, job, body.option_id)


def edit(_connection, run, body):
    state = run["state"]
    require(not state["gate_a"], "The approved plan is locked. Start another plan to change its beats.", 409)
    require("scene-beats" in state["selections"], "Choose a beat plan before editing it.", 409)
    state["beat_edit"] = validate_result("scene-beats", body.plan.model_dump(), "{}")
    state["selections"].pop("scene-brief", None)
    return state


def approve(connection, run, body):
    require(not run["state"]["gate_a"], "This plan is already approved.", 409)
    require(next_step(run) is None, "Choose a beat plan and continuity brief before approving.", 409)
    state = run["state"]
    state["gate_a"] = {"approved_at": now(), "note": body.note, "selections": dict(state["selections"]),
                       "option_id": state["option_id"], "beat_edit": state["beat_edit"]}
    mechanics = prepare_chance(connection, run, selected_result(connection, run, 'scene-beats'))
    if mechanics:
        state['gate_a']['mechanics'] = mechanics
    return state


DECISIONS = {"choose": choose, "edit": edit, "approve": approve,
             'resolve': resolve_item, 'approve-revision': approve_revision, 'repair-patch': repair_patch, 'accept': accept_scene}
