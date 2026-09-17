"""Add concentrated depth/fan-out and long-to-long paths to a separate combined fixture.

Run ``python -m tests.branch_adversarial_fixture``. No provider calls or existing
database writes are performed by the CLI. Sizes are test budgets, not product caps.
"""
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from server.branches import path_nodes
from server.database import Database, one
from tests.branch_stress_fixture import fork_at
from tests.branch_topology_fixture import TopologySize, build_topology
from tests.performance_fixture import add_pairs
from tests.topology_manifest import describe_fixture


def validate_budget(size, width):
    size.validate()
    base = sum(size.children ** level for level in range(size.generations + 1))
    if width < 3 or base + size.depth + size.siblings + width + 12 > 20000:
        raise ValueError("Adversarial fixture requires 3+ deep children within 20,000 total branches.")
    if size.longest < 4:
        raise ValueError("At least four responses are needed for distinct divergence points.")


def deep_fanout(connection, source, width):
    early = path_nodes(connection, source["head_id"])[1]["id"]
    selected = {}
    for index in range(width):
        head = source["head_id"] if index % 2 else early
        child = fork_at(connection, source, head, f"Deep wide child {index + 1:04d}")
        add_pairs(connection, child, 0, 1, f"Deep wide child {index + 1:04d}")
        if index in {0, width // 2, width - 1}:
            selected[f"deep_child_{index + 1}"] = child
    return selected


def long_path(connection, source, head, shared, total, name):
    branch = fork_at(connection, source, head, name)
    add_pairs(connection, branch, shared, total, name)
    return branch


def long_destinations(connection, child, remote, total):
    early = path_nodes(connection, child["head_id"])[1]["id"]
    base = long_path(connection, child, early, 1, total, "Long base")
    nodes = path_nodes(connection, base["head_id"])
    result = {"long_base": base}
    for label, shared in [("early", 1), ("middle", total // 2), ("late", total - 1)]:
        result[f"long_{label}"] = long_path(connection, base, nodes[shared * 2 - 1]["id"],
                                           shared, total, f"Long {label} divergence")
    result["long_remote"] = long_path(connection, remote, early, 1, total, "Long remote subtree")
    result["deep_empty"] = fork_at(connection, child, None, "Deep wide empty descendant")
    return result


def shared_prefix(left, right):
    count = 0
    for first, second in zip(left, right):
        if first != second:
            break
        count += 1
    return count


def transition_metrics(paths):
    pairs = [("long_base", f"long_{label}") for label in ["early", "middle", "late", "remote"]]
    pairs.extend([("long_early", "long_late"), ("long_middle", "long_remote")])
    result = []
    for left, right in pairs:
        common = shared_prefix(paths[left]["node_ids"], paths[right]["node_ids"])
        for source, destination in [(left, right), (right, left)]:
            result.append({"source": source, "destination": destination, "shared_messages": common,
                           "source_responses": paths[source]["responses"],
                           "destination_responses": paths[destination]["responses"],
                           "source_depth": paths[source]["depth"], "destination_depth": paths[destination]["depth"]})
    return result


def build_adversarial(database, size=TopologySize(), deep_width=1000, story=None):
    validate_budget(size, deep_width)
    baseline = build_topology(database, "combined", size, story=story)
    with database.connect(write=True) as connection:
        selected = {key: one(connection, "SELECT * FROM branches WHERE id=?", (value["id"],))
                    for key, value in baseline["paths"].items()}
        source = selected["deepest"]
        children = deep_fanout(connection, source, deep_width)
        selected.update(children)
        selected.update(long_destinations(connection, children["deep_child_1"], selected["right_leaf"], size.longest))
        connection.execute("UPDATE stories SET title=? WHERE id=?",
                           ("Branch stress · deep wide and long paths", baseline["story_id"]))
    result = describe_fixture(database, baseline["story_id"], selected, "adversarial",
                              {**asdict(size), "deep_width": deep_width})
    result["deep_parent_id"] = source["id"]
    result["transitions"] = transition_metrics(result["paths"])
    return result


def main():
    directory = Path(__file__).resolve().parents[1] / "test-results" / f"topology-adversarial-{uuid4().hex}"
    directory.mkdir(parents=True)
    database = Database(directory / "fixture.sqlite3")
    result = build_adversarial(database)
    result["database"] = str(database.path)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest), "database": str(database.path),
                      "story_id": result["story_id"], "branches": result["branch_count"],
                      "max_depth": result["max_depth"], "max_fanout": result["max_fanout"]}, indent=2))


if __name__ == "__main__":
    main()
