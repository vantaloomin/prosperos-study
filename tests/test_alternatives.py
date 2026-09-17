from uuid import uuid4

from tests.test_generations import DraftProvider, WaitingProvider, finished, generate
from tests.test_history import append
from tests.test_mechanics import configure, counts, prepare
from tests.test_profiles import make_profile


def accept(client, candidate_id, **options):
    response = client.post(f"/api/candidates/{candidate_id}/accept", json={"operation_id": uuid4().hex, **options})
    assert response.status_code == 200, response.text
    return response.json()


def change_future_configuration(client, story, profile):
    configure(client, story, chance=0, handling=True)
    prompt = next(item for item in client.get("/api/prompts").json() if item["key"] == "writer")
    assert client.put("/api/prompts/writer", json={"expected_version_id": prompt["id"],
        "template": "A future instruction, absent from earlier drafts."}).status_code == 200
    assert client.put(f"/api/profiles/{profile['profile_id']}", json={"expected_version_id": profile["id"],
        "name": "Future profile", "config": {"provider": "local", "model": "future-model"}}).status_code == 200


def test_new_telling_uses_original_inputs_after_acceptance_and_configuration_changes(client, story):
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    profile = make_profile(client, "Original writer", primary=True)
    configure(client, story, chance=100, cooldown=0)
    prepared = prepare(client, story["branch_id"])
    opportunity = client.get(f"/api/opportunities/{prepared['id']}").json()
    original = finished(client, generate(client, story)["id"])
    source = original["candidates"][0]
    accept(client, source["id"])
    append(client, story["branch_id"], "A later decision must not enter the alternative.", 1)
    change_future_configuration(client, story, profile)

    body = {"operation_id": uuid4().hex}
    route = f"/api/candidates/{source['id']}/alternatives"
    response = client.post(route, json=body)
    assert response.status_code == 201
    detail = finished(client, response.json()["id"])
    assert client.post(route, json=body).json() == response.json()
    finished(client, original["id"])

    assert len(provider.calls) == 2 and provider.calls[0] == provider.calls[1]
    assert detail["snapshot"] == original["snapshot"]
    assert len(detail["candidates"]) == 2
    assert detail["candidates"][0]["output"] == source["output"]
    assert detail["candidates"][1]["profile"] == source["profile"]
    assert detail["snapshot"]["opportunity_id"] == prepared["id"]
    assert client.get(f"/api/opportunities/{prepared['id']}").json() == opportunity
    assert counts(client)[1] == 1


def test_accepting_an_alternative_preserves_existing_continuation_and_roll_state(client, story):
    client.app.state.runner.provider = DraftProvider()
    make_profile(client, "Writer", primary=True)
    configure(client, story, cooldown=0, chance=100)
    prepared = prepare(client, story["branch_id"])
    original = finished(client, generate(client, story)["id"])
    source_id = original["candidates"][0]["id"]
    accepted = accept(client, source_id)
    append(client, story["branch_id"], "The original continuation survives.", 1)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    response = client.post(f"/api/candidates/{source_id}/alternatives", json={"operation_id": uuid4().hex})
    assert response.status_code == 201
    alternate_id = response.json()["candidate_id"]
    finished(client, original["id"])
    rejected = client.post(f"/api/candidates/{alternate_id}/accept", json={"operation_id": uuid4().hex})
    assert rejected.status_code == 409
    fork = accept(client, alternate_id, as_new_branch=True)
    branch = client.get(f"/api/branches/{fork['branch_id']}").json()

    assert fork["branch_id"] != story["branch_id"]
    assert len(branch["messages"]) == 1
    assert branch["messages"][0]["metadata"]["candidate_id"] == alternate_id
    assert branch["mechanics"]["state"]["beat"] == 1
    assert branch["mechanics"]["state"]["last_opportunity_id"] == prepared["id"]
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert accept(client, source_id) == accepted
    assert accept(client, alternate_id) == fork
    assert counts(client)[1] == 1


def test_unfinished_draft_cannot_spawn_a_new_telling(client, story):
    client.app.state.runner.provider = WaitingProvider()
    make_profile(client, "Writer", primary=True)
    run = generate(client, story)
    source_id = run["candidate_ids"][0]
    response = client.post(f"/api/candidates/{source_id}/alternatives", json={"operation_id": uuid4().hex})
    assert response.status_code == 409
    assert client.post(f"/api/candidates/{source_id}/cancel").status_code == 200
    assert len(finished(client, run["id"])["candidates"]) == 1
