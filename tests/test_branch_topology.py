from uuid import uuid4

import pytest

from server.branches import Branches
from server.database import Database
from tests.branch_topology_fixture import TopologySize, build_topology
from tests.topology_manifest import text_fingerprint


def assert_path(client, expected):
    response = client.get(f"/api/branches/{expected['id']}")
    assert response.status_code == 200
    actual = response.json()
    assert [node["id"] for node in actual["messages"]] == expected["node_ids"]
    assert actual["head_id"] == expected["head_id"]
    assert text_fingerprint(actual["messages"]) == expected["ordered_text_sha256"]
    assert len(response.content) == expected["response_json_utf8_bytes"]
    assert sum(node["role"] == "assistant" for node in actual["messages"]) == expected["responses"]
    return actual


def test_combined_topology_handles_nested_cousins_deep_short_and_long_paths(client):
    fixture = build_topology(client.app.state.database)
    assert fixture["branch_count"] == 5486
    assert fixture["max_depth"] == 1208
    assert fixture["max_fanout"] == 1003
    assert fixture["depth_distribution"][7] == 2187
    paths = fixture["paths"]
    for expected in paths.values():
        assert_path(client, expected)
    assert paths["length_0"]["messages"] == 0
    assert paths["length_3000"]["messages"] == 6000
    for length in [12, 100, 500, 3000]:
        assert paths[f"length_{length}"]["responses"] == length
        assert paths[f"length_{length}"]["depth"] == 1208
    left = assert_path(client, paths["left_leaf"])
    right = assert_path(client, paths["right_leaf"])
    assert not any("Tree 3" in node["text"] for node in left["messages"])
    assert not any("Tree 1" in node["text"] for node in right["messages"])
    payload = assert_path(client, paths["payload"])
    assert len(payload["messages"][-1]["text"]) == 100000
    assert paths["payload"]["utf16_units"] > paths["payload"]["characters"]


def test_early_edit_on_deep_descendant_preserves_all_original_paths(client):
    fixture = build_topology(client.app.state.database, size=TopologySize(generations=3, depth=12, siblings=8, longest=50))
    expected = fixture["paths"]["length_500"]
    before = assert_path(client, expected)
    response = client.post(f"/api/branches/{expected['id']}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": before["revision"],
        "node_id": expected["node_ids"][1], "replacement": "A new early possibility.", "name": "Early edit on a descendant"})
    assert response.status_code == 201
    branch_id = response.json()["branch_id"]
    edited = client.get(f"/api/branches/{branch_id}").json()
    assert edited["forked_from"] == expected["id"]
    assert len(edited["messages"]) == 2
    assert edited["messages"][0]["id"] == expected["node_ids"][0]
    assert edited["messages"][1]["text"] == "A new early possibility."
    assert_path(client, expected)
    further = client.post(f"/api/branches/{branch_id}/forks", json={"operation_id": uuid4().hex,
        "expected_revision": edited["revision"], "node_id": edited["head_id"], "name": "Further descendant"})
    assert further.status_code == 201
    assert client.get(f"/api/branches/{further.json()['branch_id']}").json()["messages"] == edited["messages"]


def test_distributed_fixture_is_reproducible_after_reopen_with_fresh_ids(tmp_path):
    size = TopologySize(generations=4)
    first_db, second_db = Database(tmp_path / "first.sqlite3"), Database(tmp_path / "second.sqlite3")
    first = build_topology(first_db, "distributed", size)
    second = build_topology(second_db, "distributed", size)
    assert first["story_id"] != second["story_id"]
    assert first["content_sha256"] == second["content_sha256"]
    assert first["depth_distribution"] == {0: 1, 1: 3, 2: 9, 3: 27, 4: 81}
    reopened = Database(first_db.path)
    for expected in first["paths"].values():
        branch = Branches(reopened).detail(expected["id"])
        assert [node["id"] for node in branch["messages"]] == expected["node_ids"]
        assert text_fingerprint(branch["messages"]) == expected["ordered_text_sha256"]


def test_fixture_growth_ceiling_is_checked_before_writing(client):
    database = client.app.state.database
    with pytest.raises(ValueError, match="safety ceiling"):
        build_topology(database, size=TopologySize(generations=10))
    assert client.get("/api/stories").json() == []
