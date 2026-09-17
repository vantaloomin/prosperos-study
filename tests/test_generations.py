import asyncio
import json
from uuid import uuid4

from server.database import decode, one
from server.generation_models import GenerateRequest
from server.generations import Generations
from server.providers.events import ProviderEvent
from tests.test_history import append
from tests.test_profiles import make_profile


class DraftProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        yield ProviderEvent(text=f"Draft from {profile['name']}.")
        yield ProviderEvent(done=True, usage={"output_tokens": 6})


class WaitingProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text="A partial beginning.")
        await asyncio.sleep(60)
        yield ProviderEvent(done=True)


def generate(client, story, profiles=None, revision=0):
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        "operation_id": uuid4().hex, "expected_revision": revision,
        "profile_ids": profiles or [], "direction": "Keep this moment quiet.",
    })
    assert response.status_code == 201
    return response.json()


def finished(client, generation_id):
    with client.stream("GET", f"/api/generations/{generation_id}/events") as stream:
        records = [json.loads(line[6:]) for line in stream.iter_lines() if line.startswith("data: ")]
    assert records
    return client.get(f"/api/generations/{generation_id}").json()


def test_comparison_freezes_identical_input_and_requires_acceptance(client, story):
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    first = make_profile(client, "First", primary=True)
    second = make_profile(client, "Second")
    run = generate(client, story, [first["profile_id"], second["profile_id"]])
    detail = finished(client, run["id"])
    assert len(provider.calls) == 2
    assert provider.calls[0][1:] == provider.calls[1][1:]
    assert all(c["status"] == "done" for c in detail["candidates"])
    assert client.get(f"/api/branches/{story['branch_id']}").json()["messages"] == []
    candidate = detail["candidates"][0]["id"]
    body = {"operation_id": uuid4().hex}
    accepted = client.post(f"/api/candidates/{candidate}/accept", json=body)
    assert accepted.status_code == 200
    assert client.post(f"/api/candidates/{candidate}/accept", json=body).json() == accepted.json()
    assert len(client.get(f"/api/branches/{story['branch_id']}").json()["messages"]) == 1
    alternate = detail["candidates"][1]["id"]
    fork = client.post(f"/api/candidates/{alternate}/accept", json={"operation_id": uuid4().hex, "as_new_branch": True}).json()
    assert fork["branch_id"] != story["branch_id"]
    assert client.get(f"/api/branches/{fork['branch_id']}").json()["messages"][0]["text"] == "Draft from Second."


def test_stale_generation_cannot_overwrite_new_history(client, story):
    client.app.state.runner.provider = DraftProvider()
    make_profile(client, "Writer", primary=True)
    run = generate(client, story)
    detail = finished(client, run["id"])
    append(client, story["branch_id"], "Something changed.", 0)
    candidate = detail["candidates"][0]["id"]
    response = client.post(f"/api/candidates/{candidate}/accept", json={"operation_id": uuid4().hex})
    assert response.status_code == 409
    assert client.get(f"/api/branches/{story['branch_id']}").json()["messages"][0]["text"] == "Something changed."


def test_stop_preserves_partial_draft_and_retry_keeps_snapshot(client, story):
    client.app.state.runner.provider = WaitingProvider()
    make_profile(client, "Writer", primary=True)
    run = generate(client, story)
    candidate = run["candidate_ids"][0]
    assert client.post(f"/api/candidates/{candidate}/cancel").status_code == 200
    stopped = finished(client, run["id"])
    assert stopped["candidates"][0]["status"] == "cancelled"
    assert stopped["candidates"][0]["output"] == "A partial beginning."
    client.app.state.runner.provider = DraftProvider()
    assert client.post(f"/api/candidates/{candidate}/retry").status_code == 200
    completed = finished(client, run["id"])
    assert completed["candidates"][0]["attempt"] == 2
    assert completed["snapshot"] == stopped["snapshot"]
    with client.app.state.database.connect() as connection:
        attempts = connection.execute("SELECT output FROM generation_attempts WHERE candidate_id=? ORDER BY attempt", (candidate,)).fetchall()
    assert len(attempts) == 2
    assert attempts[0]["output"] == "A partial beginning."


def test_profile_and_prompt_changes_do_not_rewrite_a_saved_request(client, story):
    client.app.state.runner.provider = DraftProvider()
    profile = make_profile(client, "Writer", primary=True)
    run = generate(client, story)
    before = finished(client, run["id"])
    prompt = next(item for item in client.get("/api/prompts").json() if item["key"] == "writer")
    client.put("/api/prompts/writer", json={"expected_version_id": prompt["id"], "template": "A changed instruction."})
    client.put(f"/api/profiles/{profile['profile_id']}", json={"expected_version_id": profile["id"],
               "name": "Changed", "config": {"provider": "local", "model": "different"}})
    after = client.get(f"/api/generations/{run['id']}").json()
    assert after["snapshot"] == before["snapshot"]
    assert after["candidates"][0]["profile"]["config"]["model"] == "test-model"
    with client.app.state.database.connect() as connection:
        stored = one(connection, "SELECT snapshot FROM generations WHERE id=?", (run["id"],))
    assert decode(stored["snapshot"])["prompt"]["template"] != "A changed instruction."


def test_crash_recovery_preserves_partial_attempt_before_retry(client, story):
    make_profile(client, "Writer", primary=True)
    database = client.app.state.database
    run = Generations(database).create(story["branch_id"], GenerateRequest(operation_id=uuid4().hex, expected_revision=0))
    candidate_id = run["candidate_ids"][0]
    with database.connect(write=True) as connection:
        connection.execute("UPDATE candidates SET status='running',attempt=1,output=? WHERE id=?",
                           ("Saved before the crash.", candidate_id))
    client.app.state.runner.recover()
    recovered = client.get(f"/api/generations/{run['id']}").json()
    assert recovered["candidates"][0]["status"] == "interrupted"
    client.app.state.runner.provider = DraftProvider()
    assert client.post(f"/api/candidates/{candidate_id}/retry").status_code == 200
    finished(client, run["id"])
    attempts = client.get(f"/api/candidates/{candidate_id}/attempts").json()
    assert len(attempts) == 2
    assert attempts[1]["output"] == "Saved before the crash."
    assert attempts[1]["status"] == "interrupted"
