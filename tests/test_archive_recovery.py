import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.format import TABLES
from server.database import decode, encode
from server.errors import DomainError
from server.main import create_app
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_library import create_book, publish, with_book
from tests.test_profiles import MemoryVault, make_profile
from tests.test_reviews import ReviewProvider, finished_review, review_body, start
from tests.test_sidebar import CollaboratorProvider, ask, settle, thread


def stage(client, document):
    response = client.post("/api/archives/imports", json={"content": json.dumps(document)})
    assert response.status_code == 201, response.text
    return response.json()


def saved_work(client, story):
    make_profile(client, "Archive fixture", primary=True)
    client.app.state.runner.provider = DraftProvider()
    client.app.state.review_runner.provider = ReviewProvider()
    client.app.state.side_runner.provider = CollaboratorProvider()
    node = append(client, story["branch_id"], "The original words remain.", 0)
    run = generate(client, story, revision=1)
    finished(client, run["id"])
    review, _ = start(client, story, review_body())
    report = finished_review(client, review["id"])
    selected = client.put(f"/api/reviews/{review['id']}/selection", json={"job_id": report["jobs"][0]["id"]})
    assert selected.status_code == 200
    conversation = thread(client, story)
    ask(client, conversation, story, revision=1)
    settle(client)
    return node, run, review, conversation


def test_restore_into_fresh_database_preserves_shared_dependencies_and_saved_work(client, tmp_path):
    book = create_book(client)
    character = client.post("/api/library", json={"kind": "character", "name": "Reader",
                            "content": {"lorebook_versions": [book["id"]]}}).json()
    first, second = with_book(client, character, "First"), with_book(client, character, "Second")
    publish(client, book)
    node, run, review, conversation = saved_work(client, first)
    _, document = backup(client, include_sidebar=True)
    with TestClient(create_app(tmp_path / "fresh.sqlite3"), headers={"x-roleplay-client": "workspace"}) as target:
        before_prompts = target.get("/api/prompts").json()
        staged = stage(target, document)
        assert target.get("/api/stories").json() == []
        result, mapping = restore(target, staged)
        assert len(result["story_ids"]) == 2
        assert all(item["restored_at"] for item in target.get("/api/stories").json())
        assert all(item["restored_at"] for item in target.get("/api/library").json())
        assert "restored" in target.get("/api/profiles").json()["profiles"][0]["display_name"]
        a = target.get(f"/api/branches/{mapping[first['branch_id']]}").json()
        b = target.get(f"/api/branches/{mapping[second['branch_id']]}").json()
        assert a["messages"][0]["id"] == mapping[node]
        assert a["messages"][0]["text"] == "The original words remain."
        assert a["attachments"] == b["attachments"]
        assert {item["version_id"] for item in a["attachments"]} == {mapping[character["id"]], mapping[book["id"]]}
        assert target.get(f"/api/generations/{mapping[run['id']]}").json()["candidates"][0]["output"].startswith("Draft from")
        assert target.get(f"/api/reviews/{mapping[review['id']]}").json()["jobs"][0]["status"] == "done"
        assert target.get(f"/api/side-conversations/{mapping[conversation]}").json()["turns"][0]["replies"][0]["status"] == "done"
        assert target.get("/api/prompts").json() == before_prompts
        with target.app.state.database.connect() as connection:
            assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_restore_interrupts_pending_jobs_preserves_output_and_retries_only_explicitly(client, story):
    saved_work(client, story)
    _, document = backup(client, story, include_sidebar=True)
    for table in ("candidates", "review_jobs", "side_replies"):
        document["data"][table][0].update(status="running", output="Saved partial output")
    for table in ("candidates", "review_jobs"):
        document["data"][table][0]["attempt"] += 1
    for row in document["data"]["review_runs"]:
        row["selections"] = "{}"
    staged = stage(client, document)
    writer, reviewer, sidebar = DraftProvider(), ReviewProvider(), CollaboratorProvider()
    client.app.state.runner.provider = writer
    client.app.state.review_runner.provider = reviewer
    client.app.state.side_runner.provider = sidebar
    _, mapping = restore(client, staged)
    with client.app.state.database.connect() as connection:
        for table in ("candidates", "review_jobs", "side_replies"):
            row = connection.execute(f"SELECT * FROM {table} WHERE id=?", (mapping[document["data"][table][0]["id"]],)).fetchone()
            assert row["status"] == "interrupted" and row["output"] == "Saved partial output"
    assert not writer.calls and not reviewer.calls and not sidebar.calls
    candidate = mapping[document["data"]["candidates"][0]["id"]]
    retry = client.post(f"/api/candidates/{candidate}/retry")
    assert retry.status_code == 200, retry.text
    finished(client, mapping[document["data"]["generations"][0]["id"]])
    assert len(writer.calls) == 1 and not reviewer.calls and not sidebar.calls
    attempts = client.get(f"/api/candidates/{candidate}/attempts").json()
    assert any(row["output"] == "Saved partial output" and row["status"] == "interrupted" for row in attempts)


def counts(client):
    with client.app.state.database.connect() as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (*TABLES, "operations", "archive_restores", "archive_origins")}


def test_restore_failure_rolls_back_all_records_and_same_operation_can_retry(client, story, monkeypatch):
    import server.archives.restore as importer

    insert = importer.insert_row

    def fail_after_stories(connection, table, row):
        if table == "nodes":
            raise DomainError("Fixture interrupted import", 409)
        return insert(connection, table, row)

    # Ensure failure occurs after other groups have already inserted fresh records.
    append(client, story["branch_id"], "Rollback marker", 0)
    file, _ = backup(client, story)
    before = counts(client)
    body = {"operation_id": uuid4().hex, "sha256": file["sha256"]}
    with monkeypatch.context() as patch:
        patch.setattr(importer, "insert_row", fail_after_stories)
        response = client.post(f"/api/archives/{file['id']}/restore", json=body)
    assert response.status_code == 409
    assert counts(client) == before
    assert client.post(f"/api/archives/{file['id']}/restore", json=body).status_code == 200


def test_modified_archive_file_is_rejected_before_restore(client, story):
    from server.archives.service import Archives

    file, _ = backup(client, story)
    before = counts(client)
    _, path = Archives(client.app.state.database).file(file["id"])
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    response = client.post(f"/api/archives/{file['id']}/restore", json={"operation_id": uuid4().hex, "sha256": file["sha256"]})
    assert response.status_code == 409 and counts(client) == before


def test_restored_request_reconnects_credentials_without_changing_frozen_model_or_address(client, story):
    from server.providers.service import ProviderService

    client.app.state.vault = MemoryVault()
    profile = client.post("/api/profiles", json={"name": "Cloud fixture", "make_primary": True,
                          "config": {"provider": "openai", "model": "original-model"}}).json()
    client.app.state.runner.provider = DraftProvider()
    run = generate(client, story)
    finished(client, run["id"])
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    updated = client.put(f"/api/profiles/{mapping[profile['profile_id']]}", json={
        "expected_version_id": mapping[profile["id"]], "name": "Cloud fixture", "api_key": "reconnected-test-key",
        "config": {"provider": "openai", "model": "future-model"},
    })
    assert updated.status_code == 200, updated.text
    with client.app.state.database.connect() as connection:
        candidate = connection.execute("SELECT profile FROM candidates WHERE generation_id=?", (mapping[run["id"]],)).fetchone()
        frozen = decode(candidate["profile"])
    service = ProviderService(client.app.state.vault, database=client.app.state.database)
    _, key = service.connection(frozen)
    assert key == "reconnected-test-key" and frozen["credential_ref"] is None
    assert frozen["config"]["model"] == "original-model"
    changed = client.put(f"/api/profiles/{mapping[profile['profile_id']]}", json={
        "expected_version_id": updated.json()["id"], "name": "Changed address",
        "config": {"provider": "anthropic", "model": "future-model"},
    })
    assert changed.status_code == 200, changed.text
    with pytest.raises(DomainError, match="original provider and address"):
        service.connection(frozen)


@pytest.mark.parametrize("defect", ["snapshot_story", "selected_review", "selected_reply", "duplicate_id", "disclosure"])
def test_inconsistent_archive_ownership_is_rejected(client, story, defect):
    saved_work(client, story)
    other = client.post("/api/stories", json={"title": "Other"}).json()
    _, document = backup(client, include_sidebar=True)
    data = document["data"]
    broken = deepcopy(document)
    snapshot = decode(data["generations"][0]["snapshot"])
    snapshot["branch"]["story_id"] = other["story_id"]
    mutations = {
        "snapshot_story": lambda: broken["data"]["generations"][0].update(snapshot=encode(snapshot)),
        "selected_review": lambda: broken["data"]["review_runs"][0].update(selections=encode({"review-dialogue": data["review_jobs"][0]["id"]})),
        "selected_reply": lambda: broken["data"]["side_turns"][0].update(selected_reply_id="missing-reply"),
        "duplicate_id": lambda: broken["data"]["review_runs"][0].update(id=data["generations"][0]["id"]),
        "disclosure": lambda: broken.update(include_sidebar=False),
    }
    mutations[defect]()
    before = counts(client)
    response = client.post("/api/archives/imports", json={"content": json.dumps(broken)})
    assert response.status_code in {400, 404}, response.text
    assert counts(client) == before
