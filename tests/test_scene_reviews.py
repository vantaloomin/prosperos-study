import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_library import create_book, with_book
from tests.test_profiles import make_profile
from tests.test_reviews import InvalidReviewProvider, ReviewProvider, finished_review, start
from tests.test_scene_archives import SceneRetrievalProvider
from tests.test_scene_drafting import PROSE, DraftProvider, approved_plan
from tests.test_scenes import choose, decide, get_plan, run_stage
from tests.test_sidebar import ask, settle, thread


def reviewable_plan(client, story, dialogue=False):
    scene_id, provider = approved_plan(client, story, dialogue)
    keys = ('scene-draft', 'scene-dialogue', 'scene-coverage') if dialogue else ('scene-draft', 'scene-coverage')
    for key in keys:
        choose(client, scene_id, run_stage(client, scene_id, key)[0])
    return scene_id, provider


def scene_body(client, scene_id, steps=None):
    run = get_plan(client, scene_id)
    return {"expected_revision": run["snapshot"]["branch"]["revision"], "scene_id": scene_id,
            "scene_revision": run["revision"], "steps": steps or [{"key": "review-pacing"}]}


def plan_after_history(client, story, revision):
    make_profile(client, "Scene reviewer", primary=True)
    client.app.state.scene_runner.provider = DraftProvider()
    body = {"expected_revision": revision, "operation_id": uuid4().hex, "title": "A frozen scene", "direction": "Consider the letter.", "propose_options": False}
    response = client.post(f"/api/branches/{story['branch_id']}/scenes", json=body)
    assert response.status_code == 201, response.text
    scene_id = response.json()["id"]
    for key in ("scene-beats", "scene-brief"):
        choose(client, scene_id, run_stage(client, scene_id, key)[0])
    decide(client, scene_id, "approve")
    for key in ("scene-draft", "scene-coverage"):
        choose(client, scene_id, run_stage(client, scene_id, key)[0])
    return scene_id


def test_blind_scene_readers_receive_only_two_preceding_prose_contributions(client, story):
    for index in range(3):
        append(client, story["branch_id"], f"Accepted context {index}.", index)
    response = client.post(f"/api/branches/{story['branch_id']}/messages", json={"operation_id": uuid4().hex,
        "expected_revision": 3, "role": "ooc", "text": "PRIVATE DIRECTOR GUIDANCE"})
    assert response.status_code == 201
    scene_id = plan_after_history(client, story, 4)
    client.app.state.review_runner.provider = ReviewProvider()
    steps = [{"key": key} for key in ("review-pacing", "review-rules")]
    result, _ = start(client, story, scene_body(client, scene_id, steps))
    review = finished_review(client, result["id"])
    inputs = {job["step"]: job["snapshot"]["content"] for job in review["jobs"]}
    assert "Accepted context 0." not in inputs["review-pacing"]
    assert "Accepted context 1." in inputs["review-pacing"] and "Accepted context 2." in inputs["review-pacing"]
    assert "PRIVATE DIRECTOR GUIDANCE" not in inputs["review-pacing"]
    assert "PRIVATE DIRECTOR GUIDANCE" in inputs["review-rules"]


def test_saved_draft_reviews_have_independent_scopes_and_never_accept_prose(client):
    book = create_book(client)
    story = with_book(client, book, "A reviewed proposal")
    scene_id, _ = reviewable_plan(client, story)
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    steps = [{"key": key} for key in ("review-rules", "review-continuity", "review-pacing")]
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    result, request = start(client, story, scene_body(client, scene_id, steps))
    assert client.post(f"/api/branches/{story['branch_id']}/reviews", json=request).json() == result
    review = finished_review(client, result["id"])
    assert review["current_scene_draft"] and len(provider.calls) == 3
    inputs = {job["step"]: decode(job["snapshot"]["content"]) for job in review["jobs"]}
    for context in inputs.values():
        assert context["sources"][0]["kind"] == "draft" and context["sources"][0]["text"] == PROSE
        assert "Fixture coverage" not in encode(context) and "Fixture continuity" not in encode(context)
    assert "Rain every day." in encode(inputs["review-continuity"])
    assert "Rain every day." not in encode(inputs["review-pacing"])
    assert {source["kind"] for source in inputs["review-pacing"]["sources"]} == {"draft", "previous"}
    assert "scene:approved-plan" in encode(inputs["review-rules"])
    assert "scene:approved-plan" not in encode(inputs["review-continuity"])
    assert all(job["status"] == "done" for job in review["jobs"])
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before


def test_review_requires_current_scene_complete_coverage_and_unambiguous_target(client, story):
    scene_id, provider = approved_plan(client, story)
    endpoint = f"/api/branches/{story['branch_id']}/reviews/preview"
    assert client.post(endpoint, json=scene_body(client, scene_id)).status_code == 409
    choose(client, scene_id, run_stage(client, scene_id, "scene-draft")[0])
    provider.coverage_status = "compressed"
    choose(client, scene_id, run_stage(client, scene_id, "scene-coverage")[0])
    assert client.post(endpoint, json=scene_body(client, scene_id)).status_code == 409
    provider.coverage_status = "rendered"
    choose(client, scene_id, run_stage(client, scene_id, "scene-coverage")[0])
    body = scene_body(client, scene_id)
    assert client.post(endpoint, json=body).status_code == 200
    bad = {**body, "from_node_id": get_plan(client, scene_id)["snapshot"]["branch"]["head_id"]}
    assert client.post(endpoint, json=bad).status_code == 422
    assert client.post(endpoint, json={**body, "scene_revision": None}).status_code == 422
    other = client.post("/api/stories", json={"title": "Another Story"}).json()
    assert client.post(f"/api/branches/{other['branch_id']}/reviews/preview", json=body).status_code == 409


def test_comparison_freezes_draft_and_stale_preview_cannot_start(client, story):
    scene_id, _ = reviewable_plan(client, story)
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    profiles = [make_profile(client, name)["profile_id"] for name in ("Reader A", "Reader B")]
    body = scene_body(client, scene_id, [{"key": "review-dialogue", "profile_ids": profiles}])
    result, _ = start(client, story, body)
    review = finished_review(client, result["id"])
    assert provider.calls[0][1:] == provider.calls[1][1:]
    endpoint = f"/api/branches/{story['branch_id']}/reviews"
    preview = client.post(endpoint + "/preview", json=body).json()
    replacement = run_stage(client, scene_id, "scene-draft")[0]
    request = {**body, "preview_hash": preview["preview_hash"], "operation_id": uuid4().hex}
    assert client.post(endpoint, json=request).status_code == 409
    choose(client, scene_id, replacement)
    earlier = client.get(f"/api/reviews/{result['id']}").json()
    assert not earlier["current_scene_draft"] and earlier["snapshot"] == review["snapshot"]
    assert earlier["jobs"] == review["jobs"]
    listed = client.get(endpoint, params={"scene_id": scene_id}).json()
    assert [item["id"] for item in listed] == [result["id"]]
    assert listed[0]["scene"] == {"id": scene_id, "title": "The letter"}


def test_retry_after_story_changes_preserves_original_draft_and_attempts(client, story):
    scene_id, _ = reviewable_plan(client, story)
    client.app.state.review_runner.provider = InvalidReviewProvider()
    result, _ = start(client, story, scene_body(client, scene_id))
    original = finished_review(client, result["id"])
    job = original["jobs"][0]
    assert job["status"] == "error" and job["output"]
    append(client, story["branch_id"], "Later accepted text must not enter the retry.", 1)
    provider = ReviewProvider()
    client.app.state.review_runner.provider = provider
    assert client.post(f"/api/review-jobs/{job['id']}/retry").status_code == 200
    retried = finished_review(client, result["id"])
    assert retried["jobs"][0]["status"] == "done" and not retried["current_scene_draft"]
    assert provider.calls[0][2] == job["snapshot"]["content"]
    attempts = client.get(f"/api/review-jobs/{job['id']}/attempts").json()
    assert [item["status"] for item in attempts] == ["done", "error"]
    assert attempts[1]["output"] == job["output"]


def test_collaborator_can_retrieve_a_frozen_draft_review_without_promoting_it_to_canon(client, story):
    scene_id, _ = reviewable_plan(client, story)
    client.app.state.review_runner.provider = ReviewProvider()
    result, _ = start(client, story, scene_body(client, scene_id))
    review = finished_review(client, result["id"])
    prefix = f"review:{review['jobs'][0]['id']}:"
    provider = SceneRetrievalProvider(prefix)
    client.app.state.side_runner.provider = provider
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    turn = ask(client, thread(client, story), story, revision=1)
    settle(client)
    sources = client.get(f"/api/side-turns/{turn['id']}/sources").json()
    content = "".join(item["text"] for item in sources if item["id"].startswith(prefix))
    assert '"scene":' in content and scene_id in content and PROSE in content
    assert "Review only; never accepted canon." in content and "credential_ref" not in content
    assert any(item["id"].startswith(prefix) for item in provider.calls[-1]["sources"])
    choose(client, scene_id, run_stage(client, scene_id, "scene-draft")[0])
    assert client.get(f"/api/side-turns/{turn['id']}/sources").json() == sources
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before


def test_scene_review_archive_restore_remaps_links_keeps_quotes_and_can_be_archived_again(client, story):
    scene_id, _ = reviewable_plan(client, story)
    client.app.state.review_runner.provider = ReviewProvider()
    result, _ = start(client, story, scene_body(client, scene_id))
    original = finished_review(client, result["id"])
    chosen = original["jobs"][0]["id"]
    assert client.put(f"/api/reviews/{result['id']}/selection", json={"job_id": chosen}).status_code == 200
    file, document = backup(client, story)
    assert document["version"] == 19
    restored, mapping = restore(client, file)
    review = client.get(f"/api/reviews/{mapping[result['id']]}").json()
    assert review["current_scene_draft"] and review["snapshot"]["scene"]["id"] == mapping[scene_id]
    assert review["selections"]["review-pacing"] == mapping[chosen]
    assert review["jobs"][0]["snapshot"]["content"] == original["jobs"][0]["snapshot"]["content"]
    target = {"story_id": restored["story_ids"][0], "branch_id": mapping[story["branch_id"]]}
    second, _ = backup(client, target)
    restore(client, second)
    replacement = run_stage(client, scene_id, "scene-draft")[0]
    choose(client, scene_id, replacement)
    older_file, _ = backup(client, story)
    _, older_map = restore(client, older_file)
    assert not client.get(f"/api/reviews/{older_map[result['id']]}").json()["current_scene_draft"]


@pytest.mark.parametrize("corruption", ["missing-scene", "wrong-draft", "blind-scope"])
def test_corrupt_scene_review_archives_do_not_create_stories(client, story, corruption):
    scene_id, _ = reviewable_plan(client, story)
    client.app.state.review_runner.provider = ReviewProvider()
    result, _ = start(client, story, scene_body(client, scene_id))
    finished_review(client, result["id"])
    _, document = backup(client, story)
    bad = deepcopy(document)
    if corruption == "missing-scene":
        snapshot = decode(bad["data"]["review_runs"][0]["snapshot"])
        snapshot["scene"]["id"] = "not-a-scene"
        bad["data"]["review_runs"][0]["snapshot"] = encode(snapshot)
    else:
        job = bad["data"]["review_jobs"][0]
        snapshot = decode(job["snapshot"])
        context = decode(snapshot["content"])
        if corruption == "wrong-draft":
            context["sources"][0]["text"] = "A different draft."
        else:
            context["sources"].append({"id": "hidden", "kind": "reference", "title": "Hidden", "text": "An undisclosed secret."})
        snapshot["content"] = encode(context)
        job["snapshot"] = encode(snapshot)
    before = client.get("/api/stories").json()
    assert client.post("/api/archives/imports", json={"content": json.dumps(bad)}).status_code >= 400
    assert client.get("/api/stories").json() == before
