from uuid import uuid4


def append(client, branch_id, text, revision):
    response = client.post(f"/api/branches/{branch_id}/messages", json={
        "operation_id": uuid4().hex, "expected_revision": revision, "text": text,
    })
    assert response.status_code == 201
    return response.json()["node_id"]


def test_past_edit_preserves_original_future_and_isolates_new_path(client, story):
    branch = story["branch_id"]
    first = append(client, branch, "The door is open.", 0)
    append(client, branch, "I enter the room.", 1)
    response = client.post(f"/api/branches/{branch}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": 2, "node_id": first,
        "name": "A closed door", "replacement": "The door is locked.",
    })
    assert response.status_code == 201
    fork = client.get(f"/api/branches/{response.json()['branch_id']}").json()
    original = client.get(f"/api/branches/{branch}").json()
    assert [m["text"] for m in fork["messages"]] == ["The door is locked."]
    assert [m["text"] for m in original["messages"]] == ["The door is open.", "I enter the room."]
    assert fork["messages"][0]["metadata"]["replaces"] == first


def test_repeated_request_commits_once_and_reused_id_rejects_changed_input(client, story):
    endpoint = f"/api/branches/{story['branch_id']}/messages"
    body = {"operation_id": uuid4().hex, "expected_revision": 0, "text": "One event."}
    first = client.post(endpoint, json=body)
    repeated = client.post(endpoint, json=body)
    assert first.json() == repeated.json()
    assert client.post(endpoint, json={**body, "text": "Different event."}).status_code == 409
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert len(branch["messages"]) == 1
    assert branch["revision"] == 1


def test_stale_append_and_cross_story_fork_rejected(client, story):
    other = client.post("/api/stories", json={"title": "Other"}).json()
    outsider = append(client, other["branch_id"], "A secret on another path.", 0)
    append(client, story["branch_id"], "Here.", 0)
    stale = client.post(f"/api/branches/{story['branch_id']}/messages", json={
        "operation_id": uuid4().hex, "expected_revision": 0, "text": "Stale.",
    })
    assert stale.status_code == 409
    invalid = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": 1, "node_id": outsider, "name": "Invalid",
    })
    assert invalid.status_code == 409


def test_branch_from_boundary_does_not_inherit_later_messages(client, story):
    node = append(client, story["branch_id"], "At the crossroads.", 0)
    append(client, story["branch_id"], "Turn left.", 1)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": 2, "node_id": node, "name": "Turn right",
    }).json()
    append(client, fork["branch_id"], "Turn right.", 0)
    messages = client.get(f"/api/branches/{fork['branch_id']}").json()["messages"]
    assert [m["text"] for m in messages] == ["At the crossroads.", "Turn right."]
