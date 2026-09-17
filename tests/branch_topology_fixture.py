"""Distributed and combined branch workloads; CLI always creates a disposable database.

Run with ``python -m tests.branch_topology_fixture [distributed|combined]``.
This does not alter the earlier browser-review fixture or call a model.
"""
import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from server.branches import insert_node, path_nodes, touch_branch
from server.database import Database, one
from server.models import StoryCreate
from server.stories import Stories
from tests.branch_stress_fixture import deep_path, fork_at, wide_paths
from tests.performance_fixture import add_pairs
from tests.topology_manifest import describe_fixture


@dataclass(frozen=True)
class TopologySize:
    generations: int = 7
    children: int = 3
    depth: int = 1200
    siblings: int = 1000
    longest: int = 3000
    payload_characters: int = 100000

    def validate(self):
        values = asdict(self)
        if any(value < 1 for value in values.values()):
            raise ValueError("Fixture sizes must be positive.")
        branches = sum(self.children ** level for level in range(self.generations + 1))
        if branches + self.depth + self.siblings + 6 > 20000:
            raise ValueError("This fixture's safety ceiling is 20,000 branches, not a product limit.")
        if self.longest > 10000 or self.payload_characters > 100000:
            raise ValueError("Fixture ceiling: 10,000 responses and 100,000 characters per contribution.")


def distributed_tree(connection, root, size):
    tree = {(): root}
    frontier = [()]
    for _ in range(size.generations):
        following = []
        for route in frontier:
            for ordinal in range(1, size.children + 1):
                child = (*route, ordinal)
                name = "Tree " + ".".join(map(str, child))
                source = tree[route]
                branch = fork_at(connection, source, source["head_id"], name)
                add_pairs(connection, branch, 0, ordinal % 3, name)
                tree[child] = branch
                following.append(child)
        frontier = following
    return tree


def uneven_paths(connection, source, early, longest):
    result = {}
    for responses in sorted({0, 12, 100, 500, longest}):
        branch = fork_at(connection, source, early if responses else None,
                         f"Combined length {responses}")
        if responses:
            add_pairs(connection, branch, 1, responses, f"Combined length {responses}")
        result[f"length_{responses}"] = branch
    return result


def add_payload(connection, source, early, characters):
    branch = fork_at(connection, source, early, "Combined Unicode and long paragraphs")
    fragment = "Payload marker: café e\u0301 東京 مرحبا 🌙. The letter is still sealed. "
    paragraph = fragment * 45 + "\n\n"
    text = (paragraph * (characters // len(paragraph) + 1))[:characters]
    branch["head_id"] = insert_node(connection, branch, text, "assistant",
                                    {"source": "branch_topology_fixture", "marker": "payload"})
    touch_branch(connection, branch["id"], branch["head_id"])
    return branch


def combined_paths(connection, tree, size):
    root = tree[()]
    early = path_nodes(connection, root["head_id"])[1]["id"]
    deepest = deep_path(connection, tree[(1,) * size.generations], size.depth)
    wide = wide_paths(connection, tree[(size.children,)], early, size.siblings)
    result = {"deepest": deepest, "last_sibling": wide}
    result.update(uneven_paths(connection, deepest, early, size.longest))
    result["payload"] = add_payload(connection, tree[(size.children,) * size.generations],
                                    early, size.payload_characters)
    return result


def build_topology(database, mode="combined", size=TopologySize(), story=None):
    size.validate()
    if mode not in {"distributed", "combined"}:
        raise ValueError("Choose the distributed or combined fixture.")
    story = story or Stories(database).create(StoryCreate(
        title=f"Branch topology · {mode} benchmark",
        premise="Isolated deterministic topology and text fixture. No model calls or user content."))
    with database.connect(write=True) as connection:
        root = one(connection, "SELECT * FROM branches WHERE id=?", (story["branch_id"],))
        add_pairs(connection, root, 0, 12, "Topology shared beginning")
        tree = distributed_tree(connection, root, size)
        selected = {"root": root, "left_parent": tree[(1,) * (size.generations - 1)],
                    "left_leaf": tree[(1,) * size.generations],
                    "right_leaf": tree[(size.children,) * size.generations]}
        if mode == "combined":
            selected.update(combined_paths(connection, tree, size))
    return describe_fixture(database, story["story_id"], selected, mode, asdict(size))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["distributed", "combined"], default="combined")
    mode = parser.parse_args().mode
    directory = Path(__file__).resolve().parents[1] / "test-results" / f"topology-{mode}-{uuid4().hex}"
    directory.mkdir(parents=True)
    database = Database(directory / "fixture.sqlite3")
    result = build_topology(database, mode)
    result["database"] = str(database.path)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest), "database": str(database.path),
                      "story_id": result["story_id"], "branches": result["branch_count"],
                      "max_depth": result["max_depth"], "max_fanout": result["max_fanout"]}, indent=2))


if __name__ == "__main__":
    main()
