from uuid import uuid4

from tests.branch_stress_fixture import build_stress


def test_deep_wide_unequal_paths_remain_isolated_and_allow_further_forks(client):
    fixture = build_stress(client.app.state.database)
    story = client.get(f"/api/stories/{fixture['story_id']}").json()
    assert len(story["branches"]) == 2206 and fixture["max_depth"] == 1201
    longest = client.get(f"/api/branches/{fixture['paths']['length_3000']['id']}").json()
    assert len(longest["messages"]) == 6000
    assert longest["messages"][-1]["id"] == fixture["paths"]["length_3000"]["head_id"]
    assert not any("Unique sibling" in message["text"] for message in longest["messages"])
    deepest = fixture["paths"]["deepest"]
    source = client.get(f"/api/branches/{deepest['id']}").json()
    fork = client.post(f"/api/branches/{deepest['id']}/forks", json={"operation_id": uuid4().hex,
        "expected_revision": source["revision"], "node_id": deepest["first_node_id"], "name": "Another early fork at depth 1201"})
    assert fork.status_code == 201, fork.text
    result = client.get(f"/api/branches/{fork.json()['branch_id']}").json()
    assert result["forked_from"] == deepest["id"]
    assert [node["id"] for node in result["messages"]] == [deepest["first_node_id"]]
    assert client.get(f"/api/branches/{deepest['id']}").json()["messages"] == source["messages"]
