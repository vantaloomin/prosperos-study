"""Validate frozen scene-review ownership and the prose actually reviewed."""
from server.archives.plan_scans import validate_plan_scan
from server.archives.scenes import validate_state
from server.archives.source_memory import canon_assets, validate_historical_memory
from server.archives.summary_context import validate_summary_context
from server.database import decode, many
from server.errors import require
from server.memory.source_replay import replay_sources
from server.scenes.context import draft_view
from server.scenes.drafts import coverage_passes
from server.scenes.reviews import scoped_scene_sources
from server.scenes.state import run_record, selected_result
from server.workflow.catalog import ROLE_MAP
from server.workflow.runner import parse_review


def comparable(sources):
    return [{key: source[key] for key in ("kind", "title", "text")} for source in sources]


def validate_review_target(connection, row, snapshot):
    target = snapshot["scene"]
    origin = run_record(connection, target["id"])
    require(row["branch_id"] == origin["branch_id"] == snapshot["branch"]["id"], "A draft review refers to another branch's scene.")
    original_branch = origin["snapshot"]["branch"]
    require(all(snapshot["branch"][key] == original_branch[key] for key in ("head_id", "revision", "manifest_id")),
            "A draft review's accepted context differs from its scene's starting point.")
    require(0 <= target["revision"] <= origin["revision"], "A draft review has an invalid scene revision.")
    require(target["state"]["gate_a"], "A draft review has no approved scene plan.")
    require(not snapshot.get("from_node_id") and not snapshot.get("through_node_id"), "A draft review also names a Story passage.")
    frozen = {**origin, "state": target["state"], "revision": target["revision"]}
    validate_state(connection, frozen)
    require(coverage_passes(selected_result(connection, frozen, "scene-coverage")) or "scene-coverage" in frozen["snapshot"].get("disabled_steps", []), "A draft review lacks completed coverage.")
    draft = draft_view(connection, frozen)
    require(draft and draft["complete"], "A draft review refers to incomplete prose.")
    return frozen, draft


def validate_draft_reviews(connection, document):
    for row in document["data"]["review_runs"]:
        snapshot = decode(row["snapshot"])
        if snapshot.get('purpose') == 'planned-continuity-v1':
            validate_plan_scan(connection, row, snapshot)
            continue
        if not snapshot.get("scene"):
            for job in many(connection, "SELECT * FROM review_jobs WHERE run_id=?", (row["id"],)):
                validate_historical_memory(connection, row, snapshot, job)
            continue
        frozen, draft = validate_review_target(connection, row, snapshot)
        jobs = many(connection, "SELECT * FROM review_jobs WHERE run_id=?", (row["id"],))
        for job in jobs:
            role = ROLE_MAP[job["step"]]
            inputs = decode(job["snapshot"])
            context = decode(inputs["content"])
            decisions = frozen["snapshot"].get("author_memory") if role["scope"] != "blind" else None
            require(context.get("author_memory") == decisions, "A reviewer changed its frozen author decisions or role scope.")
            expected = scoped_scene_sources(connection, role, frozen, draft)
            projection = replay_sources({"scope": role["scope"], "sources": expected, **({"author_memory": decisions} if decisions else {})},
                                        inputs, frozen["snapshot"].get("summary_aids", {}),
                                        canon_assets(connection, frozen["snapshot"]["branch"]["manifest_id"], inputs))
            validate_summary_context(connection, inputs, frozen["snapshot"]["branch"], frozen["snapshot"].get("memory_policy", {}))
            expected = projection["sources"]
            require(all(context.get(key) == projection.get(key) for key in ("memory_guidance", "canon_guidance")), "Review memory guidance was altered.")
            # Imported inputs retain their original source IDs. Match authority, order and exact text.
            require(comparable(context["sources"]) == comparable(expected), "A draft review's sources disagree with its frozen target or role scope.")
            if job["status"] == "done":
                require(parse_review(job["output"], inputs["content"]) == decode(job["result"]), "A saved draft report disagrees with its validated output.")
