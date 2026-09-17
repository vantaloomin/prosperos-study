"""Measure fixture contents, independently of branch navigation timing."""
import hashlib
from collections import Counter, defaultdict

from server.branches import Branches
from server.database import encode, many


def topology_summary(branches):
    children = defaultdict(list)
    for branch in branches:
        children[branch["forked_from"]].append(branch["id"])
    depths = {}
    pending = [(branch_id, 0) for branch_id in children[None]]
    while pending:
        branch_id, depth = pending.pop()
        if branch_id in depths:
            raise ValueError("The fixture contains a branch cycle.")
        depths[branch_id] = depth
        pending.extend((child, depth + 1) for child in children[branch_id])
    if len(depths) != len(branches):
        raise ValueError("The fixture contains unreachable ancestry.")
    return {"branch_count": len(branches), "max_depth": max(depths.values()),
            "max_fanout": max(len(value) for key, value in children.items() if key is not None),
            "depth_distribution": dict(sorted(Counter(depths.values()).items()))}, depths


def text_fingerprint(messages):
    digest = hashlib.sha256()
    for message in messages:
        digest.update(encode([message["role"], message["text"]]).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def path_metrics(branch, depth):
    messages = branch["messages"]
    return {"id": branch["id"], "name": branch["name"], "depth": depth,
            "head_id": branch["head_id"], "manifest_id": branch["manifest_id"],
            "node_ids": [node["id"] for node in messages],
            "messages": len(messages), "responses": sum(node["role"] == "assistant" for node in messages),
            "characters": sum(len(node["text"]) for node in messages),
            "utf16_units": sum(len(node["text"].encode("utf-16-le")) // 2 for node in messages),
            "text_utf8_bytes": sum(len(node["text"].encode("utf-8")) for node in messages),
            "response_json_utf8_bytes": len(encode(branch).encode("utf-8")),
            "attachments_json_utf8_bytes": len(encode(branch["attachments"]).encode("utf-8")),
            "ordered_text_sha256": text_fingerprint(messages)}


def describe_fixture(database, story_id, selected, mode, sizes):
    with database.connect() as connection:
        branches = many(connection, "SELECT * FROM branches WHERE story_id=? ORDER BY rowid", (story_id,))
        nodes = many(connection, "SELECT role,text FROM nodes WHERE story_id=? ORDER BY rowid", (story_id,))
    topology, depths = topology_summary(branches)
    paths = {key: path_metrics(Branches(database).detail(branch["id"]), depths[branch["id"]])
             for key, branch in selected.items()}
    return {"fixture_version": 1, "mode": mode, "sizes": sizes, "story_id": story_id,
            **topology, "unique_nodes": len(nodes), "unique_characters": sum(len(node["text"]) for node in nodes),
            "unique_text_utf8_bytes": sum(len(node["text"].encode("utf-8")) for node in nodes),
            "content_sha256": text_fingerprint(nodes), "paths": paths,
            "limitations": ["No saved alternatives, RNG, reviews, sidebar or attached lore in this cohort.",
                            "Counts and content checks do not measure browser responsiveness."]}
