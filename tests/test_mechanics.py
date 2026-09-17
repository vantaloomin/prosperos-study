from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode
from server.mechanics.engine import resolve_beat
from server.mechanics.models import Attempt, Beat, RngSettings
from server.mechanics.randomness import Draws
from server.mechanics.state import initial_state
from server.mechanics.table_engine import TableSet
from server.mechanics.tables import catalog
from tests.test_generations import DraftProvider, finished, generate
from tests.test_profiles import make_profile


@pytest.fixture
def versions(client):
    with client.app.state.database.connect() as connection:
        return catalog(connection)


class FixedDraws:
    values = []

    def __init__(self, _seed):
        self.log = []
        self.remaining = iter(self.values)

    def die(self, sides, stream, purpose):
        value = next(self.remaining)
        assert 1 <= value <= sides
        self.log.append({"sides": sides, "stream": stream, "purpose": purpose, "result": value})
        return value


def fixed(monkeypatch, values):
    monkeypatch.setattr("server.mechanics.engine.Draws", FixedDraws)
    monkeypatch.setattr(FixedDraws, "values", values)


def configure(client, story, **values):
    revision = client.get(f"/api/stories/{story['story_id']}").json()["revision"]
    response = client.put(f"/api/stories/{story['story_id']}/randomness", json={
        "expected_revision": revision, "settings": {"enabled": True, **values}})
    assert response.status_code == 200, response.text
    return response.json()["settings"]


def prepare(client, branch_id, revision=0, **values):
    body = {"operation_id": uuid4().hex, "expected_revision": revision,
            "beat": {"label": "A completed exchange"}, **values}
    response = client.post(f"/api/branches/{branch_id}/opportunities", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def accept_manual(client, branch_id, opportunity_id, revision=0):
    response = client.post(f"/api/branches/{branch_id}/messages", json={
        "operation_id": uuid4().hex, "expected_revision": revision, "role": "narrator",
        "text": "The conversation finds its natural pause.", "opportunity_id": opportunity_id})
    assert response.status_code == 201, response.text
    return response.json()


def counts(client):
    with client.app.state.database.connect() as connection:
        return [connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ["nodes", "mechanic_opportunities", "node_mechanics"]]


def test_complete_distributions_and_intentional_no_event_faces(versions):
    assert len(versions) == 30
    for table in versions.values():
        definition = table["definition"]
        faces = [face for row in definition["rows"] for face in range(row["low"], row["high"] + 1)]
        assert sorted(faces) == list(range(1, definition["die"] + 1))
    expected = {"encounter": [3, 4], "atmosphere": [2], "obstacle": [2], "momentum": [1],
                "micro-friction": [1], "complication": [1], "transition-pressure": [1], "anomaly": [1]}
    for key, faces in expected.items():
        actual = [face for row in versions[key]["definition"]["rows"] if row["kind"] == "no_event"
                  for face in range(row["low"], row["high"] + 1)]
        assert actual == faces
    assert "Proposed completion" in versions["dramatic-turn"]["definition"]["note"]


def test_exclusions_preserve_relative_weights_and_disabled_child_dependencies(versions):
    settings = RngSettings(disabled_tables=["anomaly"], excluded_rows={"narrative-push": ["result-16"]})
    tables = TableSet(versions, settings)
    odds = {row["id"]: row for row in tables.odds("narrative-push")}
    assert odds["result-96"]["percent"] == odds["result-16"]["percent"] == 0
    assert odds["result-1"]["percent"] == 25  # 15 original faces out of 60 remaining.
    assert odds["result-51"]["percent"] == pytest.approx(100 * 25 / 60)
    assert sum(row["percent"] for row in odds.values()) == pytest.approx(100)
    settings.disabled_tables = ["handling-cost"]
    assert len(tables.available("handling", False)) == 7  # Shape off must not exclude the base band.


def test_event_draws_do_not_shift_handling_stream():
    left, right = Draws("same frozen seed"), Draws("same frozen seed")
    for _ in range(20):
        left.die(100, "events", "extra gate")
    assert [left.die(100, "handling", "base") for _ in range(20)] == [
        right.die(100, "handling", "base") for _ in range(20)]
    # Fixed interoperability vector, independently checked with Node's SHA-256 implementation.
    assert Draws("same frozen seed").die(100, "handling", "base") == 46


def test_reordered_editor_rows_still_obey_the_numbered_faces(versions, monkeypatch):
    tables = deepcopy(versions)
    tables["narrative-push"]["definition"]["rows"].reverse()
    fixed(monkeypatch, [10])
    result = TableSet(tables, RngSettings()).face("narrative-push", FixedDraws("seed"), "events")
    assert result["face"] == 10 and result["row"]["id"] == "result-1"


def test_disabled_tables_leave_no_hidden_beat_or_cooldown_effect(versions):
    settings = RngSettings(enabled=True, disabled_tables=["narrative-push"])
    before = initial_state()
    result = resolve_beat(versions, settings, Beat(label="Complete"), before, "seed")
    assert result["after"] == before
    assert result["draws"] == []


def test_handling_child_no_event_stops_carrier_and_progression(versions, monkeypatch):
    tables = deepcopy(versions)
    tables["handling-bonus"]["definition"]["rows"][0]["kind"] = "no_event"
    fixed(monkeypatch, [95, 10, 1])
    beat = Beat(label="A chosen attempt", family="none", attempt=Attempt(action="Read the chart", actor="Mara", domain="Study", level=4))
    result = resolve_beat(tables, RngSettings(enabled=True, handling=True), beat, initial_state(), "seed")
    assert result["handling"]["status"] == "no_event"
    assert len(result["draws"]) == 3
    assert result["after"]["domains"] == {}
    assert result["after"]["handling_history"] == []


def test_child_no_event_cancels_parent_and_starts_cooldown(versions, monkeypatch):
    fixed(monkeypatch, [1, 16, 1])
    settings = RngSettings(enabled=True, cooldown=3)
    state = {**initial_state(), "cooldown": 0}
    result = resolve_beat(versions, settings, Beat(label="A pause"), state, "fixed")
    assert result["event"]["status"] == "no_event"
    assert [part["table_id"] for part in result["event"]["chain"]] == ["narrative-push", "micro-friction"]
    assert result["writer"]["event"] is None
    assert result["after"]["cooldown"] == 3
    assert result["after"]["unresolved_event"] is False
    assert len(result["draws"]) == 3
    assert state["cooldown"] == 0


def test_cadence_uses_beats_shared_across_families_and_miss_does_not_reset(versions, monkeypatch):
    fixed(monkeypatch, [100])
    settings, state = RngSettings(enabled=True), initial_state()
    for family in ["narrative-push", "encounter", "narrative-push"]:
        result = resolve_beat(versions, settings, Beat(label="Complete", family=family), state, "fixed")
        assert result["draws"] == []
        state = result["after"]
    result = resolve_beat(versions, settings, Beat(label="Complete"), state, "fixed")
    assert result["event"]["status"] == "miss"
    assert result["after"]["cooldown"] == 0
    assert result["after"]["beat"] == 4


@pytest.mark.parametrize("field", ["waiting_for_player", "protected"])
def test_ineligible_beats_do_not_draw_or_advance(versions, field):
    before = initial_state()
    result = resolve_beat(versions, RngSettings(enabled=True), Beat(label="Still deciding", **{field: True}), before, "seed")
    assert result["before"] == result["after"] == before
    assert result["draws"] == []
    assert result["writer"] == {}


def test_major_suppression_keeps_original_draws_without_replacement(versions, monkeypatch):
    fixed(monkeypatch, [100, 2])
    before = {**initial_state(), "major_events": 1}
    result = resolve_beat(versions, RngSettings(enabled=True), Beat(label="Complete"), before, "seed", manual=True)
    assert result["event"]["status"] == "suppressed"
    assert len(result["draws"]) == 2
    assert result["event"]["chain"][0]["face"] == 100
    assert result["after"]["major_events"] == 1
    assert result["writer"]["event"] is None


def test_pressure_cap_precedes_overflow_and_disabled_components_make_no_draws(versions, monkeypatch):
    fixed(monkeypatch, [95, 20])
    settings = RngSettings(enabled=True, handling=True, subresults=False, carriers=False)
    beat = Beat(label="A chosen attempt", family="none", attempt=Attempt(action="Read the chart", actor="Mara", domain="Study", level=5))
    before = {**initial_state(), "handling_history": [81, 96]}
    result = resolve_beat(versions, settings, beat, before, "seed")
    handling = result["handling"]
    assert (handling["uncapped"], handling["total"], handling["capped"]) == (115, 75, True)
    assert handling["band"]["id"] == "intended"
    assert handling["domain_change"] is None
    assert len(result["draws"]) == 2


@pytest.mark.parametrize("raw,modifier,level,band,after", [(1, 10, -4, "catastrophe", -5), (99, 8, 4, "legend", 5)])
def test_unclamped_extremes_propose_bounded_domain_progression(versions, monkeypatch, raw, modifier, level, band, after):
    fixed(monkeypatch, [raw, modifier])
    settings = RngSettings(enabled=True, handling=True, subresults=False, carriers=False)
    beat = Beat(label="A chosen attempt", family="none", attempt=Attempt(action="Read the chart", actor="Mara", domain="Study", level=level))
    result = resolve_beat(versions, settings, beat, initial_state(), "seed")
    assert result["handling"]["band"]["id"] == band
    assert result["after"]["domains"]["mara:study"] == after
    assert result["before"]["domains"] == {}
    assert "total" not in result["writer"]["handling"]


def test_off_generates_no_mechanics(client, story):
    make_profile(client, "Writer", primary=True)
    client.app.state.runner.provider = DraftProvider()
    run = generate(client, story)
    detail = finished(client, run["id"])
    assert detail["snapshot"]["opportunity_id"] is None
    assert counts(client) == [0, 0, 0]


def test_excluded_exceptional_result_is_suppressed_without_progression_or_replacement(versions, monkeypatch):
    fixed(monkeypatch, [99, 8])
    settings = RngSettings(enabled=True, handling=True, excluded_rows={"handling": ["legend"]})
    beat = Beat(label="A chosen attempt", family="none", attempt=Attempt(action="Read the chart", actor="Mara", domain="Study", level=4))
    result = resolve_beat(versions, settings, beat, initial_state(), "seed")
    assert result["handling"]["status"] == "suppressed"
    assert result["handling"]["total"] == 107
    assert len(result["draws"]) == 2
    assert result["after"]["domains"] == {}
    assert result["after"]["handling_history"] == []


def test_legacy_onboarding_off_stays_readable_and_new_settings_are_validated(client, story):
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE stories SET settings=? WHERE id=?", ('{"randomness":"off"}', story["story_id"]))
    branch = client.get(f"/api/branches/{story['branch_id']}")
    assert branch.status_code == 200
    assert branch.json()["mechanics"]["enabled"] is False
    context = client.get(f"/api/branches/{story['branch_id']}/mechanics")
    assert context.status_code == 200 and context.json()["settings"]["enabled"] is False
    assert client.post("/api/stories", json={"title": "Invalid", "settings": {"randomness": "surprise"}}).status_code == 409


def test_preview_changes_no_story_state(client, story):
    body = {"seed": "preview-check"}
    first = client.post("/api/roll-tables/encounter/preview", json=body)
    second = client.post("/api/roll-tables/encounter/preview", json=body)
    assert first.json() == second.json()
    assert first.json()["preview_only"] is True
    assert counts(client) == [0, 0, 0]


def test_prepared_beat_is_frozen_until_explicit_acceptance_and_historical_edit_excludes_it(client, story):
    configure(client, story)
    first = prepare(client, story["branch_id"])
    again = prepare(client, story["branch_id"])
    assert again["id"] == first["id"] and again["reused"]
    assert counts(client) == [0, 1, 0]
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert before["mechanics"]["state"]["beat"] == 0
    accepted = accept_manual(client, story["branch_id"], first["id"])
    current = client.get(f"/api/branches/{story['branch_id']}").json()
    assert current["mechanics"]["state"]["beat"] == 1
    assert current["mechanics"]["state"]["cooldown"] == 2
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={"operation_id": uuid4().hex,
        "expected_revision": 1, "node_id": accepted["node_id"], "name": "Earlier possibility", "replacement": "An edited exchange."}).json()
    edited = client.get(f"/api/branches/{fork['branch_id']}").json()
    assert edited["mechanics"]["state"]["beat"] == 0
    assert client.get(f"/api/branches/{story['branch_id']}").json()["mechanics"]["state"]["beat"] == 1


def test_comparisons_and_fresh_prose_reuse_rolls_and_hide_numeric_log(client, story):
    client.app.state.runner.provider = DraftProvider()
    first = make_profile(client, "First", primary=True)
    second = make_profile(client, "Second")
    configure(client, story, cooldown=0, chance=100)
    prepared = prepare(client, story["branch_id"])
    run = generate(client, story, [first["profile_id"], second["profile_id"]])
    detail = finished(client, run["id"])
    repeat = finished(client, generate(client, story)["id"])
    assert detail["snapshot"]["opportunity_id"] == repeat["snapshot"]["opportunity_id"] == prepared["id"]
    content = decode(detail["snapshot"]["content"])
    assert "randomness" not in content["story"]["settings"]
    assert "draws" not in content["prepared_beat"]
    assert "seed" not in content["prepared_beat"]
    assert counts(client)[1] == 1
    for index, candidate in enumerate(detail["candidates"]):
        response = client.post(f"/api/candidates/{candidate['id']}/accept", json={"operation_id": uuid4().hex,
            "as_new_branch": index > 0}).json()
        branch = client.get(f"/api/branches/{response['branch_id']}").json()
        assert branch["mechanics"]["state"]["last_opportunity_id"] == prepared["id"]
        assert branch["mechanics"]["state"]["beat"] == 1


def test_manual_roll_works_with_master_off_and_reroll_preserves_original_path(client, story):
    first = prepare(client, story["branch_id"], manual=True)
    before = client.get(f"/api/opportunities/{first['id']}").json()
    reroll = prepare(client, story["branch_id"], manual=True, reroll_of=first["id"])
    assert reroll["branch_id"] != story["branch_id"]
    after = client.get(f"/api/opportunities/{reroll['id']}").json()
    assert after["snapshot"]["seed"] != before["snapshot"]["seed"]
    assert after["snapshot"]["reroll_of"] == first["id"]
    assert client.get(f"/api/opportunities/{first['id']}").json() == before
    assert counts(client) == [0, 2, 0]


def test_table_versions_stay_pinned_and_invalid_edits_are_rejected(client, story, versions):
    settings = configure(client, story)
    table = versions["momentum"]
    definition = deepcopy(table["definition"])
    definition["rows"][1]["instruction"] = "An existing participant offers an opening."
    body = {"operation_id": uuid4().hex, "expected_version_id": table["id"], "definition": definition}
    response = client.put("/api/roll-tables/momentum", json=body)
    assert response.status_code == 200
    context = client.get(f"/api/branches/{story['branch_id']}/mechanics").json()
    assert next(item for item in context["tables"] if item["table_id"] == "momentum")["id"] == table["id"]
    definition["rows"][1]["low"] = 1
    assert client.put("/api/roll-tables/momentum", json={**body, "operation_id": uuid4().hex}).status_code == 422
    definition["rows"][1]["low"] = 2
    definition["rows"][1]["child"] = "narrative-push"
    body.update(operation_id=uuid4().hex, expected_version_id=response.json()["id"])
    assert client.put("/api/roll-tables/momentum", json=body).status_code == 400
    assert settings["table_versions"]["momentum"] == table["id"]


def test_ooc_cannot_accept_mechanics_and_stale_preparation_is_explicit(client, story):
    configure(client, story)
    prepared = prepare(client, story["branch_id"])
    body = {"operation_id": uuid4().hex, "expected_revision": 0, "text": "An aside.", "role": "ooc", "opportunity_id": prepared["id"]}
    assert client.post(f"/api/branches/{story['branch_id']}/messages", json=body).status_code == 400
    configure(client, story, chance=25)
    body.update(operation_id=uuid4().hex, role="narrator")
    assert client.post(f"/api/branches/{story['branch_id']}/messages", json=body).status_code == 409
    assert counts(client) == [0, 1, 0]
