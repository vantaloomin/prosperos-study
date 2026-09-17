import asyncio
import json
from uuid import uuid4

import pytest

from server.database import decode, one
from server.errors import DomainError
from server.providers.events import ProviderEvent
from server.workflow.runner import parse_review
from tests.test_history import append
from tests.test_library import create_book, publish, with_book
from tests.test_profiles import make_profile


class ReviewProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        source = decode(content)["sources"][0]
        yield ProviderEvent(text=json.dumps({"summary": "Test fixture review; no model was called.", "findings": [
            {"severity": "soft", "source_id": source["id"], "quote": source["text"],
             "explanation": "Fixture evidence check.", "suggestion": "Consider the detail."}]}), done=True)


class InvalidReviewProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text='{"summary":"Invalid source","findings":[{"severity":"hard","source_id":"hidden:other-branch",'
                                '"quote":"invented","explanation":"unsupported","suggestion":"change it"}]}', done=True)


class WaitingReviewProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text="Partial review preserved.")
        await asyncio.sleep(60)


def review_body(revision=1, steps=None):
    return {"expected_revision": revision, "steps": steps or [{"key": "review-plausibility"}]}


def start(client, story, body):
    route = f"/api/branches/{story['branch_id']}/reviews"
    preview = client.post(f"{route}/preview", json=body)
    assert preview.status_code == 200, preview.text
    request = {**body, "preview_hash": preview.json()["preview_hash"], "operation_id": uuid4().hex}
    result = client.post(route, json=request)
    assert result.status_code == 201, result.text
    return result.json(), request


def finished_review(client, run_id):
    with client.stream("GET", f"/api/reviews/{run_id}/events") as response:
        records = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
    assert records
    return records[-1]


def test_review_role_scope_excludes_future_branches_mechanics_and_other_reviewers(client, story):
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    make_profile(client, "Writer", primary=True)
    opening = append(client, story["branch_id"], "The door is locked.", 0)
    ending = append(client, story["branch_id"], "The key is still in her pocket.", 1)
    append(client, story["branch_id"], "FUTURE_DO_NOT_INCLUDE", 2)
    body = review_body(3, [{"key": "review-plausibility"}, {"key": "review-continuity"}])
    body.update(from_node_id=ending, through_node_id=ending)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    run, _ = start(client, story, body)
    result = finished_review(client, run["id"])
    assert all(job["status"] == "done" for job in result["jobs"])
    assert len(provider.calls) == 2
    for _, _, content in provider.calls:
        assert "FUTURE_DO_NOT_INCLUDE" not in content
        assert "prepared_beat" not in content and "draws" not in content
        assert {item["id"] for item in decode(content)["sources"]} == {f"message:{opening}", f"message:{ending}"}
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert client.post(f"/api/candidates/{result['jobs'][0]['id']}/accept", json={"operation_id": uuid4().hex}).status_code == 404


def test_blind_review_omits_lore_and_continuity_keeps_historical_reference_version(client):
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    make_profile(client, "Writer", primary=True)
    book = create_book(client)
    story = with_book(client, book, "A versioned scene")
    append(client, story["branch_id"], "An old scene.", 0)
    publish(client, book)
    run, _ = start(client, story, review_body(steps=[{"key": "review-pacing"}, {"key": "review-continuity"}]))
    results = finished_review(client, run["id"])["jobs"]
    inputs = {job["step"]: job["snapshot"]["content"] for job in results}
    assert "Rain every day." not in inputs["review-pacing"]
    assert "Rain every day." in inputs["review-continuity"]
    assert all("A dry season." not in content for content in inputs.values())


def test_explicit_comparison_freezes_matching_inputs_and_selection_is_only_review_state(client, story):
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    first = make_profile(client, "First", primary=True)
    second = make_profile(client, "Second")
    append(client, story["branch_id"], "The first line stays unchanged.", 0)
    body = review_body(steps=[{"key": "review-dialogue", "profile_ids": [first["profile_id"], second["profile_id"]]}])
    run, request = start(client, story, body)
    result = finished_review(client, run["id"])
    assert client.post(f"/api/branches/{story['branch_id']}/reviews", json=request).json() == run
    finished_review(client, run["id"])
    assert len(provider.calls) == 2 and provider.calls[0][1:] == provider.calls[1][1:]
    job = result["jobs"][1]
    assert "credential_ref" not in job["snapshot"]["profile"]
    selection = client.put(f"/api/reviews/{run['id']}/selection", json={"job_id": job["id"]})
    assert selection.json()["selections"] == {"review-dialogue": job["id"]}
    assert len(client.get(f"/api/branches/{story['branch_id']}").json()["messages"]) == 1


def test_preview_rejects_changed_inputs_before_any_provider_request(client, story):
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    make_profile(client, "Writer", primary=True)
    append(client, story["branch_id"], "A scene to review.", 0)
    body = review_body()
    route = f"/api/branches/{story['branch_id']}/reviews"
    preview = client.post(f"{route}/preview", json=body).json()
    prompt = next(item for item in client.get("/api/prompts").json() if item["key"] == "review-plausibility")
    assert client.put("/api/prompts/review-plausibility", json={"expected_version_id": prompt["id"], "template": "Changed instructions."}).status_code == 200
    result = client.post(route, json={**body, "operation_id": uuid4().hex, "preview_hash": preview["preview_hash"]})
    assert result.status_code == 409
    assert provider.calls == [] and client.get(route).json() == []


def test_invalid_review_citation_is_preserved_for_inspection_and_retry(client, story):
    client.app.state.review_runner.provider = InvalidReviewProvider()
    make_profile(client, "Writer", primary=True)
    append(client, story["branch_id"], "A scene to review.", 0)
    run, _ = start(client, story, review_body())
    job = finished_review(client, run["id"])["jobs"][0]
    assert job["status"] == "error" and job["result"] is None
    assert "outside" in job["error"] and "hidden:other-branch" in job["output"]
    client.app.state.review_runner.provider = ReviewProvider()
    assert client.post(f"/api/review-jobs/{job['id']}/retry").status_code == 200
    retried = finished_review(client, run["id"])["jobs"][0]
    assert retried["status"] == "done" and retried["attempt"] == 2
    assert retried["snapshot"] == job["snapshot"]
    attempts = client.get(f"/api/review-jobs/{job['id']}/attempts").json()
    assert len(attempts) == 2 and attempts[1]["output"] == job["output"]


def test_stop_and_restart_preserve_review_attempts(client, story):
    client.app.state.review_runner.provider = WaitingReviewProvider()
    make_profile(client, "Writer", primary=True)
    append(client, story["branch_id"], "A scene to review.", 0)
    run, _ = start(client, story, review_body())
    job_id = run["job_ids"][0]
    assert client.post(f"/api/review-jobs/{job_id}/cancel").status_code == 200
    job = finished_review(client, run["id"])["jobs"][0]
    assert job["status"] == "cancelled" and job["output"] == "Partial review preserved."
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE review_jobs SET status='running' WHERE id=?", (job_id,))
    client.app.state.review_runner.recover()
    with client.app.state.database.connect() as connection:
        recovered = one(connection, "SELECT * FROM review_jobs WHERE id=?", (job_id,))
    assert recovered["status"] == "interrupted" and recovered["output"] == job["output"]


def test_saved_step_profiles_inherit_primary_and_retain_explicit_overrides(client, story):
    first = make_profile(client, "First", primary=True)
    second = make_profile(client, "Second")
    third = make_profile(client, "Third")
    route = f"/api/stories/{story['story_id']}/workflow"
    saved = client.put(route, json={"expected_revision": 0, "step_profiles": {"review-dialogue": second["profile_id"]}})
    assert saved.status_code == 200
    assert client.put("/api/profiles/primary", json={"profile_id": third["profile_id"]}).status_code == 200
    view = client.get(route).json()
    steps = {step["key"]: step["effective_profile_id"] for step in view["steps"]}
    assert steps["writer"] == steps["review-rules"] == third["profile_id"]
    assert steps["review-dialogue"] == second["profile_id"]
    assert first["profile_id"] != view["effective_primary_id"]
    assert client.put(route, json={"expected_revision": 0, "step_profiles": {}}).status_code == 409


def test_review_requires_verbatim_evidence_from_the_named_source():
    content = json.dumps({"sources": [{"id": "message:one", "text": "The lamp stays lit."}]})
    report = {"summary": "Unsupported contradiction", "findings": [{"severity": "hard", "source_id": "message:one",
              "quote": "The lamp goes out.", "explanation": "Invented evidence", "suggestion": "Change it."}]}
    with pytest.raises(DomainError, match="quotation does not match"):
        parse_review(json.dumps(report), content)


def test_review_ranges_reject_foreign_nodes_and_reverse_order_before_generation(client, story):
    make_profile(client, "Writer", primary=True)
    first = append(client, story["branch_id"], "First.", 0)
    last = append(client, story["branch_id"], "Last.", 1)
    other = client.post("/api/stories", json={"title": "Another story"}).json()
    foreign = append(client, other["branch_id"], "Do not read this.", 0)
    route = f"/api/branches/{story['branch_id']}/reviews"
    assert client.post(f"{route}/preview", json={**review_body(2), "through_node_id": foreign}).status_code == 409
    assert client.post(f"{route}/preview", json={**review_body(2), "from_node_id": last, "through_node_id": first}).status_code == 400
    assert client.get(route).json() == []


def test_review_capacity_failure_never_silently_drops_sources(client, story):
    make_profile(client, "Writer", primary=True)
    append(client, story["branch_id"], "A deliberately long passage. " * 1600, 0)
    route = f"/api/branches/{story['branch_id']}/reviews"
    response = client.post(f"{route}/preview", json=review_body())
    assert response.status_code == 409 and "No sources were silently dropped" in response.json()["detail"]
    assert client.get(route).json() == []
