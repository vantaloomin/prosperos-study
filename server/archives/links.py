"""Validate ownership links that SQLite foreign keys alone cannot express."""
from server.database import decode, one
from server.errors import require


def validate_ownership(connection, document):
    data = document["data"]
    ids = [row["id"] for table, rows in data.items() if table != "roll_tables" for row in rows if "id" in row]
    require(len(ids) == len(set(ids)), "Archive record identifiers must be unique across record groups.")
    require(document["scope"] != "story" or len(data["stories"]) == 1, "A Story archive must contain exactly one Story.")
    require(document["include_sidebar"] or not data["side_threads"], "This archive's sidebar disclosure is inconsistent.")
    for row in data["roll_tables"]:
        version = one(connection, "SELECT table_id FROM roll_table_versions WHERE id=?", (row["version_id"],))
        require(version["table_id"] == row["id"], "A table head belongs to a different table.")
    for key, version_id in document["prompt_heads"].items():
        version = one(connection, "SELECT key FROM prompt_versions WHERE id=?", (version_id,))
        require(version["key"] == key, "A prompt head belongs to a different role.")
    validate_run_links(connection, data)
    validate_selections(connection, data)
    validate_acceptance(connection, data)


def owned(connection, table, record_id, story_id):
    row = one(connection, f"SELECT * FROM {table} WHERE id=?", (record_id,))
    require(row["story_id"] == story_id, "A saved record refers to another Story's history.")
    return row


def snapshot_links(connection, snapshot, story_id):
    branch = snapshot["branch"]
    owned(connection, "branches", branch["id"], story_id)
    require(branch["story_id"] == story_id, "A saved branch snapshot belongs to another Story.")
    owned(connection, "manifests", branch["manifest_id"], story_id)
    if snapshot.get('background_state_id'):
        owned(connection, 'background_states', snapshot['background_state_id'], story_id)
    if snapshot.get('memory_controls_version_id'):
        owned(connection, 'memory_control_versions', snapshot['memory_controls_version_id'], story_id)
    if snapshot.get('writer_snapshot'):
        snapshot_links(connection, snapshot['writer_snapshot'], story_id)
    for node_id in [branch["head_id"], snapshot.get("from_node_id"), snapshot.get("through_node_id")]:
        if node_id:
            owned(connection, "nodes", node_id, story_id)


def validate_run_links(connection, data):
    for table in ("generations", "review_runs", "mechanic_opportunities", "scene_runs", 'assessment_runs', 'background_runs', 'summary_runs'):
        for row in data[table]:
            branch = one(connection, "SELECT story_id FROM branches WHERE id=?", (row["branch_id"],))
            snapshot_links(connection, decode(row["snapshot"]), branch["story_id"])
    for row in data["side_turns"]:
        thread = one(connection, "SELECT story_id FROM side_threads WHERE id=?", (row["thread_id"],))
        snapshot_links(connection, decode(row["snapshot"]), thread["story_id"])
    for row in data["node_mechanics"]:
        opportunity = decode(row["state"]).get("last_opportunity_id")
        if opportunity:
            node = one(connection, "SELECT story_id FROM nodes WHERE id=?", (row["node_id"],))
            owned(connection, "mechanic_opportunities", opportunity, node["story_id"])


def validate_selections(connection, data):
    for row in data["review_runs"]:
        for step, job_id in decode(row["selections"]).items():
            job = one(connection, "SELECT * FROM review_jobs WHERE id=?", (job_id,))
            require(job["run_id"] == row["id"] and job["step"] == step and job["status"] == "done",
                    "A selected review is not a completed result from this run and role.")
    for row in data["side_turns"]:
        if row["selected_reply_id"]:
            reply = one(connection, "SELECT * FROM side_replies WHERE id=?", (row["selected_reply_id"],))
            require(reply["turn_id"] == row["id"], "A selected sidebar reply belongs to another turn.")


def validate_acceptance(connection, data):
    for row in data["candidates"]:
        require(bool(row["accepted_node_id"]) == bool(row["accepted_branch_id"]), "A saved acceptance link is incomplete.")
        if not row["accepted_node_id"]:
            continue
        origin = one(connection, "SELECT b.story_id FROM generations g JOIN branches b ON b.id=g.branch_id WHERE g.id=?",
                     (row["generation_id"],))
        owned(connection, "nodes", row["accepted_node_id"], origin["story_id"])
        owned(connection, "branches", row["accepted_branch_id"], origin["story_id"])
