from uuid import uuid4

from tests.test_history import append


def create_book(client):
    response = client.post("/api/library", json={
        "kind": "lorebook", "name": "The city", "content": {"text": "Rain every day."},
    })
    assert response.status_code == 201
    return response.json()


def with_book(client, book, name):
    return client.post("/api/stories", json={"title": name, "settings": {"disabled_prompts": []}, "attachments": [{
        "asset_id": book["asset_id"], "version_id": book["id"],
    }]}).json()


def publish(client, book):
    response = client.post(f"/api/library/{book['asset_id']}/versions", json={
        "expected_version_id": book["id"], "name": "The city", "content": {"text": "A dry season."},
    })
    assert response.status_code == 201
    return response.json()


def adoption_request(preview):
    return {"operation_id": uuid4().hex, "targets": [
        {key: target[key] for key in ("story_id", "expected_revision", "manifest_id")}
        for target in preview["targets"]]}


def test_published_edit_is_pinned_then_bulk_push_preserves_historical_versions(client):
    book = create_book(client)
    a, b = with_book(client, book, "A"), with_book(client, book, "B")
    old_node = append(client, a["branch_id"], "It rains.", 0)
    next_version = publish(client, book)
    before = client.get(f"/api/stories/{a['story_id']}").json()
    assert before["attachments"][0]["version_id"] == book["id"]
    assert before["attachments"][0]["update_available"]
    c = with_book(client, next_version, "C")
    endpoint = f"/api/versions/{next_version['id']}/adoption"
    preview = client.get(endpoint).json()
    body = adoption_request(preview)
    assert client.post(endpoint, json=body).json() == {"updated": 2}
    assert client.post(endpoint, json=body).json() == {"updated": 2}
    for item in (a, b, c):
        current = client.get(f"/api/stories/{item['story_id']}").json()
        assert current["attachments"][0]["version_id"] == next_version["id"]
    fork = client.post(f"/api/branches/{a['branch_id']}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": 2, "node_id": old_node,
        "name": "Historical", "replacement": "It still rains.",
    }).json()
    history = client.get(f"/api/branches/{fork['branch_id']}").json()
    assert history["attachments"][0]["version_id"] == book["id"]
    assert len(client.get(f"/api/library/{book['asset_id']}/versions").json()) == 2


def test_bulk_update_rejects_stale_target_set_without_partial_changes(client):
    book = create_book(client)
    a = with_book(client, book, "A")
    version = publish(client, book)
    endpoint = f"/api/versions/{version['id']}/adoption"
    body = adoption_request(client.get(endpoint).json())
    with_book(client, book, "Newly attached")
    assert client.post(endpoint, json=body).status_code == 409
    current = client.get(f"/api/stories/{a['story_id']}").json()
    assert current["attachments"][0]["version_id"] == book["id"]


def test_mismatched_asset_version_is_rejected(client):
    first, second = create_book(client), create_book(client)
    response = client.post("/api/stories", json={"title": "Bad reference", "attachments": [{
        "asset_id": first["asset_id"], "version_id": second["id"],
    }]})
    assert response.status_code == 400
    assert client.get("/api/stories").json() == []


def test_nested_lorebook_is_pinned_and_conflicts_fail_atomically(client):
    book = create_book(client)
    character = client.post("/api/library", json={
        "kind": "character", "name": "Reader", "content": {"lorebook_versions": [book["id"]]},
    }).json()
    story = with_book(client, character, "Nested")
    detail = client.get(f"/api/stories/{story['story_id']}").json()
    assert {a["version_id"] for a in detail["attachments"]} == {book["id"], character["id"]}
    version = publish(client, book)
    endpoint = f"/api/versions/{version['id']}/adoption"
    body = adoption_request(client.get(endpoint).json())
    assert client.post(endpoint, json=body).status_code == 400
    assert client.get(f"/api/stories/{story['story_id']}").json()["revision"] == 0
