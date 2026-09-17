from uuid import uuid4

from server.database import encode, one
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_profiles import make_profile


def export(client, branch_id, revision, **options):
    return client.post(f"/api/branches/{branch_id}/transcript", json={"expected_revision": revision, **options})


def test_transcript_uses_only_selected_path_and_does_not_mutate(client, story):
    branch = story["branch_id"]
    first = append(client, branch, "At the crossroads", 0)
    append(client, branch, "LEFT continuation", 1)
    fork = client.post(f"/api/branches/{branch}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": 2, "node_id": first, "name": "Right",
    }).json()["branch_id"]
    second = append(client, fork, "RIGHT continuation", 0)
    before = client.get(f"/api/branches/{fork}").json()
    with client.app.state.database.connect() as connection:
        operations = one(connection, "SELECT COUNT(*) AS count FROM operations")["count"]
    whole = export(client, fork, 1).json()
    assert "At the crossroads" in whole["content"] and "RIGHT continuation" in whole["content"]
    assert "LEFT continuation" not in whole["content"]
    passage = export(client, fork, 1, from_node_id=second, through_node_id=second).json()
    assert passage["message_count"] == 1 and "At the crossroads" not in passage["content"]
    assert client.get(f"/api/branches/{fork}").json() == before
    with client.app.state.database.connect() as connection:
        assert one(connection, "SELECT COUNT(*) AS count FROM operations")["count"] == operations


def test_transcript_omits_private_material_and_resolves_frozen_model(client, story):
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    profile = make_profile(client, "Writer", primary=True)
    run = generate(client, story)
    candidate = finished(client, run["id"])["candidates"][0]["id"]
    client.post(f"/api/candidates/{candidate}/accept", json={"operation_id": uuid4().hex})
    client.post(f"/api/branches/{story['branch_id']}/messages", json={
        "operation_id": uuid4().hex, "expected_revision": 1, "role": "ooc", "text": "PRIVATE OOC",
    })
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE stories SET premise=?,settings=? WHERE id=?",
                           ("PRIVATE PREMISE", encode({"hidden": "PRIVATE STATE"}), story["story_id"]))
    response = client.put(f"/api/profiles/{profile['profile_id']}", json={
        "expected_version_id": profile["id"], "name": "Changed", "config": {"provider": "local", "model": "future-model"},
    })
    assert response.status_code == 200
    default = export(client, story["branch_id"], 2).json()
    assert default["message_count"] == 1 and default["omitted_ooc_count"] == 1
    assert "PRIVATE" not in default["content"] and "test-model" not in default["content"]
    detailed = export(client, story["branch_id"], 2, include_models=True, include_ooc=True, include_timestamps=True).json()
    assert "PRIVATE OOC" in detailed["content"] and "test-model" in detailed["content"]
    assert "future" not in detailed["content"] and "PREMISE" not in detailed["content"]
    assert "STATE" not in detailed["content"] and len(provider.calls) == 1
    timestamp = client.get(f"/api/branches/{story['branch_id']}").json()["messages"][0]["created_at"]
    assert timestamp in detailed["content"]


def test_transcript_rejects_stale_reversed_and_foreign_ranges(client, story):
    first = append(client, story["branch_id"], "First", 0)
    second = append(client, story["branch_id"], "Second", 1)
    other = client.post("/api/stories", json={"title": "Other"}).json()
    outsider = append(client, other["branch_id"], "Elsewhere", 0)
    assert export(client, story["branch_id"], 1).status_code == 409
    assert export(client, story["branch_id"], 2, from_node_id=second, through_node_id=first).status_code == 400
    assert export(client, story["branch_id"], 2, from_node_id=outsider).status_code == 409
    assert export(client, story["branch_id"], 2, include_hidden=True).status_code == 422


def test_empty_transcript_and_literal_markdown_are_safe_to_share(client, story):
    empty = export(client, story["branch_id"], 0).json()
    assert empty["message_count"] == 0
    assert "No contributions" in empty["content"]
    append(client, story["branch_id"], '<script>alert("x")</script>\n# *literal* [link](file:///secret)', 0)
    result = export(client, story["branch_id"], 1).json()
    assert "<script>" not in result["content"] and "&lt;script&gt;" in result["content"]
    assert r"\# \*literal\* \[link\]" in result["content"]
    assert result["filename"].startswith("roleplay-") and result["filename"].endswith(".md")


def test_download_is_exact_prepared_text_even_after_the_branch_changes(client, story):
    append(client, story["branch_id"], "The prepared words.", 0)
    prepared = export(client, story["branch_id"], 1).json()
    assert export(client, story["branch_id"], 1).json()["download_url"] == prepared["download_url"]
    append(client, story["branch_id"], "Later text must stay out of this download.", 1)
    download = client.get(prepared["download_url"])
    assert download.status_code == 200 and download.text == prepared["content"]
    assert "Later text" not in download.text
    assert download.headers["content-type"].startswith("text/markdown")
    assert download.headers["content-disposition"].startswith("attachment; filename*=UTF-8''roleplay-")
    with client.app.state.database.connect() as connection:
        assert one(connection, "SELECT COUNT(*) AS n FROM prepared_transcripts")["n"] == 1
