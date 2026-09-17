"""Reproducible branch topology stress data. CLI writes only browser-review.sqlite3."""
import json
from pathlib import Path

from server.branches import insert_node, path_nodes, touch_branch
from server.database import Database, one
from server.models import StoryCreate
from server.stories import Stories, create_branch
from tests.performance_fixture import add_pairs


def fork_at(connection, source, head_id, name):
    branch_id = create_branch(connection, source["story_id"], source["manifest_id"], name)
    connection.execute("UPDATE branches SET head_id=?,forked_from=?,fork_node_id=? WHERE id=?",
                       (head_id, source["id"], head_id, branch_id))
    return one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))


def deep_path(connection, source, depth):
    current = source
    for level in range(1, depth + 1):
        current = fork_at(connection, current, current["head_id"], f"Nested {level:04d}")
        add_pairs(connection, current, level - 1, level, f"Depth {level}")
    return current


def wide_paths(connection, source, head_id, width):
    last = source
    for index in range(1, width + 1):
        last = fork_at(connection, source, head_id, f"Sibling {index:04d}")
        last["head_id"] = insert_node(connection, last, f"Unique sibling {index}. No neighboring branch shares this line.",
                                      "assistant", {"source": "branch_stress_fixture"})
        touch_branch(connection, last["id"], last["head_id"])
    return last


def path_summary(connection, branch):
    nodes = path_nodes(connection, branch["head_id"])
    return {"id": branch["id"], "name": branch["name"], "messages": len(nodes),
            "responses": sum(node["role"] == "assistant" for node in nodes),
            "characters": sum(len(node["text"]) for node in nodes),
            "head_id": branch["head_id"], "first_node_id": nodes[0]["id"] if nodes else None}


def build_stress(database, depth=1200, width=1000, longest=3000):
    story = Stories(database).create(StoryCreate(title="Branch stress · nested, wide & uneven",
        premise=f"Isolated benchmark: {depth} nested forks, {width} siblings, paths up to {longest} responses. No model calls."))
    with database.connect(write=True) as connection:
        root = one(connection, "SELECT * FROM branches WHERE id=?", (story["branch_id"],))
        add_pairs(connection, root, 0, 120, "Shared root")
        nodes = path_nodes(connection, root["head_id"])
        early = nodes[1]["id"]
        deepest = deep_path(connection, root, depth)
        widest = wide_paths(connection, root, early, width)
        selected = {"baseline": root, "deepest": deepest, "last_sibling": widest}
        for responses in [0, 12, 100, 500, longest]:
            branch = fork_at(connection, deepest, early if responses else None, f"Uneven · {responses} responses")
            if responses:
                add_pairs(connection, branch, 1, responses, f"Uneven {responses}")
            selected[f"length_{responses}"] = branch
        middle = one(connection, "SELECT * FROM branches WHERE story_id=? AND name=?", (story["story_id"], f"Nested {max(1, depth // 2):04d}"))
        selected["middle"] = middle
        branches = connection.execute("SELECT COUNT(*) FROM branches WHERE story_id=?", (story["story_id"],)).fetchone()[0]
        unique_nodes = connection.execute("SELECT COUNT(*) FROM nodes WHERE story_id=?", (story["story_id"],)).fetchone()[0]
        return {"story_id": story["story_id"], "branch_count": branches, "max_depth": depth + 1, "fanout": width,
                "unique_nodes": unique_nodes, "paths": {key: path_summary(connection, branch) for key, branch in selected.items()}}


if __name__ == "__main__":
    root_path = Path(__file__).resolve().parents[1]
    result = build_stress(Database(root_path / "data" / "browser-review.sqlite3"))
    destination = root_path / "test-results" / f"branch-stress-{result['story_id']}.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
