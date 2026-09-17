import pytest

from server.database import Database, many
from tests.branch_adversarial_fixture import build_adversarial
from tests.branch_topology_fixture import TopologySize
from tests.test_branch_topology import assert_path


def small_size():
    return TopologySize(generations=3, depth=8, siblings=10, longest=24, payload_characters=1200)


def test_long_destinations_share_exact_early_middle_late_prefixes(client):
    fixture = build_adversarial(client.app.state.database, small_size(), deep_width=20)
    paths = fixture["paths"]
    for key in ["long_base", "long_early", "long_middle", "long_late", "long_remote"]:
        assert paths[key]["responses"] == 24
        assert_path(client, paths[key])
    forward = {item["destination"]: item for item in fixture["transitions"] if item["source"] == "long_base"}
    assert {key: value["shared_messages"] for key, value in forward.items()} == {
        "long_early": 2, "long_middle": 24, "long_late": 46, "long_remote": 2}
    assert paths["long_base"]["depth"] == 13
    assert paths["long_remote"]["depth"] == 4
    for transition in fixture["transitions"]:
        assert transition["source_responses"] == transition["destination_responses"] == 24


def test_deep_parent_has_wide_children_and_reachable_further_descendants(client):
    database = client.app.state.database
    fixture = build_adversarial(database, small_size(), deep_width=20)
    with database.connect() as connection:
        children = many(connection, "SELECT * FROM branches WHERE forked_from=?", (fixture["deep_parent_id"],))
    # Five earlier unequal-history branches remain, alongside the new twenty.
    assert len(children) == 25
    assert fixture["max_depth"] == 14
    assert fixture["max_fanout"] == 25
    paths = fixture["paths"]
    assert paths["deep_child_1"]["responses"] == 2
    assert paths["deep_child_20"]["responses"] > paths["deep_child_1"]["responses"]
    assert paths["deep_empty"]["messages"] == 0
    assert paths["deep_empty"]["depth"] == 13
    for path in paths.values():
        assert_path(client, path)
    remote = assert_path(client, paths["long_remote"])
    assert not any("Long base" in message["text"] for message in remote["messages"])


def test_adversarial_fixture_content_and_transition_sizes_are_reproducible(tmp_path):
    first = build_adversarial(Database(tmp_path / "first.sqlite3"), small_size(), 3)
    second = build_adversarial(Database(tmp_path / "second.sqlite3"), small_size(), 3)
    assert first["story_id"] != second["story_id"]
    assert first["content_sha256"] == second["content_sha256"]
    assert first["transitions"] == second["transitions"]


@pytest.mark.parametrize("size,width", [(TopologySize(), 20000), (small_size(), 2),
                                        (TopologySize(longest=3), 3)])
def test_invalid_adversarial_budget_is_rejected_before_story_creation(client, size, width):
    with pytest.raises(ValueError):
        build_adversarial(client.app.state.database, size, width)
    assert client.get("/api/stories").json() == []
