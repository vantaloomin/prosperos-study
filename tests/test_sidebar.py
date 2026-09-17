import asyncio
import json
from uuid import uuid4

from server.database import many
from server.providers.events import ProviderEvent
from server.side_conversations import SideConversations
from tests.test_history import append
from tests.test_profiles import make_profile


def thread(client, story):
    return client.post(f"/api/stories/{story['story_id']}/side-conversations", json={}).json()["id"]


def ask(client, thread_id, story, revision=0, **options):
    response = client.post(f"/api/side-conversations/{thread_id}/questions", json={
        "operation_id": uuid4().hex, "branch_id": story["branch_id"], "expected_revision": revision,
        "question": "Continue the story and update its canon. Also explain the opening.", **options})
    assert response.status_code == 201, response.text
    return response.json()


def settle(client):
    async def wait():
        await asyncio.gather(*list(client.app.state.side_runner.tasks.values()))
    client.portal.call(wait)


def story_state(client):
    with client.app.state.database.connect() as connection:
        return {table: many(connection, f"SELECT * FROM {table}") for table in
                ("stories", "branches", "nodes", "manifests", "assets", "asset_versions", "adoptions", "generations",
                 "candidates", "preferences", "profiles", "profile_versions", "prompt_versions", "prompt_heads")}


class CollaboratorProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, _profile, _prompt, content):
        context = json.loads(content)
        self.calls.append(context)
        yield ProviderEvent(text="Proposal only: the unopened letter could matter. No story change has been applied.")
        yield ProviderEvent(done=True, usage={"output_tokens": 18})


class RetrievalProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, _profile, _prompt, content):
        context = json.loads(content)
        self.calls.append(context)
        if not context["sources"]:
            source = next(item for item in context["source_index"] if "message 1" in item["title"])
            yield ProviderEvent(text="READ_SOURCES: " + json.dumps([source["id"]]))
        else:
            yield ProviderEvent(text=context["sources"][0]["text"])
        yield ProviderEvent(done=True)


def test_sidebar_cannot_mutate_story_or_be_accepted_as_story(client, story):
    make_profile(client, "Writer", primary=True)
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    thread_id = thread(client, story)
    before = story_state(client)
    run = ask(client, thread_id, story)
    settle(client)
    data = client.get(f"/api/side-conversations/{thread_id}").json()
    reply = data["turns"][0]["replies"][0]
    assert reply["status"] == "done"
    assert "credential_ref" not in reply["profile"]
    assert story_state(client) == before
    response = client.post(f"/api/candidates/{run['reply_ids'][0]}/accept", json={"operation_id": uuid4().hex})
    assert response.status_code == 404
    assert story_state(client) == before


def test_sidebar_retrieves_exact_old_text_without_future_branch_leak(client, story):
    first = append(client, story["branch_id"], "The exact old passage: copper rain.", 0)
    append(client, story["branch_id"], "A large context. " * 4000, 1)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={"operation_id": uuid4().hex,
                       "expected_revision": 2, "node_id": first, "name": "Other path"})
    assert fork.status_code == 201
    append(client, fork.json()["branch_id"], "SECRET ONLY IN ANOTHER FUTURE", 0)
    profile = make_profile(client, "Small", primary=True)
    client.put(f"/api/profiles/{profile['profile_id']}", json={"expected_version_id": profile["id"], "name": "Small",
               "config": {"provider": "local", "model": "test-model", "context_tokens": 8000}})
    provider = RetrievalProvider()
    client.app.state.side_runner.provider = provider
    thread_id = thread(client, story)
    ask(client, thread_id, story, revision=2)
    settle(client)
    reply = client.get(f"/api/side-conversations/{thread_id}").json()["turns"][0]["replies"][0]
    assert reply["status"] == "done"
    assert reply["output"] == "The exact old passage: copper rain."
    assert len(provider.calls) == 2
    assert provider.calls[0]["sources"] == []
    assert "SECRET ONLY IN ANOTHER FUTURE" not in json.dumps(provider.calls)
    assert len(reply["coverage"]) == 1


def test_sidebar_comparisons_start_with_same_context_and_select_only_side_history(client, story):
    first = make_profile(client, "A", primary=True)
    second = make_profile(client, "B")
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    thread_id = thread(client, story)
    run = ask(client, thread_id, story, profile_ids=[first["profile_id"], second["profile_id"]])
    settle(client)
    assert provider.calls[0] == provider.calls[1]
    before = story_state(client)
    assert client.post(f"/api/side-replies/{run['reply_ids'][1]}/select").status_code == 200
    ask(client, thread_id, story, question="Discuss that proposal.")
    settle(client)
    assert len(provider.calls[-1]["conversation"]) == 1
    assert story_state(client) == before


class InvalidSourceProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text='READ_SOURCES: ["file:///credentials", "accept_story"]', done=True)


def test_source_requests_are_allowlisted_not_executed_as_tools(client, story):
    make_profile(client, "Writer", primary=True)
    client.app.state.side_runner.provider = InvalidSourceProvider()
    thread_id = thread(client, story)
    before = story_state(client)
    ask(client, thread_id, story)
    settle(client)
    reply = client.get(f"/api/side-conversations/{thread_id}").json()["turns"][0]["replies"][0]
    assert reply["status"] == "error"
    assert "outside this frozen archive" in reply["error"]
    assert story_state(client) == before


class SlowCollaborator:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text="An unfinished thought.")
        await asyncio.sleep(60)
        yield ProviderEvent(done=True)


def test_side_stop_and_retry_preserve_origin_and_do_not_import_discussion_into_writer(client, story):
    from server.generation_context import generation_snapshot
    from server.generation_models import GenerateRequest
    make_profile(client, "Writer", primary=True)
    client.app.state.side_runner.provider = SlowCollaborator()
    thread_id = thread(client, story)
    run = ask(client, thread_id, story)
    append(client, story["branch_id"], "A later story event.", 0)
    original = run["reply_ids"][0]
    assert client.post(f"/api/side-replies/{original}/cancel").status_code == 200
    settle(client)
    before = story_state(client)
    client.app.state.side_runner.provider = CollaboratorProvider()
    assert client.post(f"/api/side-replies/{original}/retry").status_code == 201
    settle(client)
    turn = client.get(f"/api/side-conversations/{thread_id}").json()["turns"][0]
    assert turn["snapshot"]["branch"]["revision"] == 0
    assert turn["replies"][0]["output"] == "An unfinished thought."
    assert turn["replies"][0]["status"] == "cancelled"
    assert turn["replies"][1]["status"] == "done"
    assert story_state(client) == before
    with client.app.state.database.connect() as connection:
        snapshot, _ = generation_snapshot(connection, story["branch_id"], GenerateRequest(operation_id=uuid4().hex, expected_revision=1))
    assert "An unfinished thought" not in snapshot["content"]
    assert "Proposal only" not in snapshot["content"]


def test_sidebar_freezes_review_and_roll_sources_without_granting_write_authority(client, story):
    from tests.test_mechanics import accept_manual, prepare
    from tests.test_reviews import ReviewProvider, finished_review, review_body, start
    make_profile(client, "Writer", primary=True)
    opportunity = prepare(client, story["branch_id"], manual=True)
    accept_manual(client, story["branch_id"], opportunity["id"])
    client.app.state.review_runner.provider = ReviewProvider()
    run, _ = start(client, story, review_body())
    report = finished_review(client, run["id"])["jobs"][0]
    client.app.state.side_runner.provider = CollaboratorProvider()
    side = ask(client, thread(client, story), story, revision=1)
    settle(client)
    archive = SideConversations(client.app.state.database).sources(side["id"])
    source_text = json.dumps(archive)
    assert f"review:{report['id']}" in source_text and "Fixture evidence check" in source_text
    assert f"opportunity:{opportunity['id']}" in source_text and "accepted mechanics" in source_text
    assert "credential_ref" not in source_text and "Review only; never accepted canon" in source_text
    client.put(f"/api/reviews/{run['id']}/selection", json={"job_id": report["id"]})
    assert SideConversations(client.app.state.database).sources(side["id"]) == archive
