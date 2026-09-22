import base64
import json
import sqlite3
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from server.archives.format import ARCHIVE_VERSION, INSPIRATION_TABLES, V53_TABLES
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.inspiration.models import Card
from server.main import create_app
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_profiles import make_profile


def content():
    return {'cards': [
        {'id': 'quiet', 'title': 'A seat', 'text': '  Leave a place open.\n', 'tags': ['quiet'], 'weight': 0.25},
        {'id': 'loud', 'title': 'A knock', 'text': '<script>literal()</script> 🌙', 'tags': ['urgent'], 'weight': 0.75},
        {'id': 'disabled', 'title': 'Not today', 'text': 'Do not draw.', 'weight': 100, 'enabled': False},
    ]}


def create(client, **overrides):
    body = {'operation_id': uuid4().hex, 'name': 'Small choices', 'content': content(), **overrides}
    response = client.post('/api/inspiration/decks', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/inspiration/decks', json=body).json() == response.json()
    return response.json()


def draw(client, version, **overrides):
    body = {'operation_id': uuid4().hex, **overrides}
    response = client.post(f"/api/inspiration/versions/{version['id']}/draws", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def pack_source(client, versions):
    response = client.post('/api/inspiration/packs/export', json={'name': 'My collection', 'version_ids': [item['id'] for item in versions]})
    assert response.status_code == 200, response.text
    return response.json()


def stage(client, document):
    raw = b'\xef\xbb\xbf' + json.dumps(document, ensure_ascii=False, indent=2).encode()
    response = client.post('/api/inspiration/packs', json={'filename': 'collection.json', 'source_base64': base64.b64encode(raw).decode()})
    assert response.status_code == 201, response.text
    return response.json(), raw


def import_pack(client, report, **overrides):
    body = {'operation_id': uuid4().hex, 'source_sha256': report['source_sha256'], 'reviewed': True,
            'choices': [{'key': item['key']} for item in report['decks']], **overrides}
    response = client.post(f"/api/inspiration/packs/{report['id']}/publish", json=body)
    assert response.status_code == 201, response.text
    assert client.post(f"/api/inspiration/packs/{report['id']}/publish", json=body).json() == response.json()
    return response.json()


def test_deck_lifecycle_preserves_versions_ids_and_stale_updates(client):
    first = create(client, unsupported={'future': {'weighting': 'reference only'}})
    assert first['content']['cards'][0]['text'] == '  Leave a place open.\n'
    body = {'operation_id': uuid4().hex, 'name': 'Revised deck', 'expected_version_id': first['id'],
            'content': {'cards': [{**first['content']['cards'][0], 'text': 'Revised words.'}]}}
    endpoint = f"/api/inspiration/decks/{first['deck_id']}/versions"
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    second = response.json()
    assert second['number'] == 2 and second['content']['cards'][0]['id'] == 'quiet'
    assert second['unsupported'] == first['unsupported']
    assert client.post(endpoint, json=body).json() == second
    assert client.post(endpoint, json={**body, 'operation_id': uuid4().hex}).status_code == 409
    assert client.get(f"/api/inspiration/versions/{first['id']}").json()['content'] == first['content']
    copied = create(client, content=first['content'], name='My separate copy')
    assert copied['deck_id'] != first['deck_id'] and copied['content'] == first['content']
    archived = client.put(f"/api/inspiration/decks/{first['deck_id']}/archived", json={
        'operation_id': uuid4().hex, 'expected_revision': second['revision'], 'archived': True})
    assert archived.status_code == 200
    assert len(client.get('/api/inspiration/decks').json()) == 1
    assert len(client.get('/api/inspiration/decks?include_archived=true').json()) == 2
    assert client.post(f"/api/inspiration/versions/{first['id']}/draws", json={'operation_id': uuid4().hex}).status_code == 400
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            connection.execute('UPDATE inspiration_versions SET name=? WHERE id=?', ('changed', first['id']))


def test_exact_odds_filters_seeded_previews_and_no_story_changes(client, story):
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    body = {'content': content(), 'seed': 'harbor', 'count': 100}
    response = client.post('/api/inspiration/preview', json=body)
    assert response.status_code == 200, response.text
    first = response.json()
    assert client.post('/api/inspiration/preview', json=body).json() == first
    assert [row['probability'] for row in first['selection']['cards']] == [
        {'numerator': 250000, 'denominator': 1000000}, {'numerator': 750000, 'denominator': 1000000}, {'numerator': 0, 'denominator': 1000000}]
    assert first['selection']['replacement'] and first['recorded'] is False
    filtered = client.post('/api/inspiration/preview', json={**body, 'filters': {'tags': ['quiet']}}).json()
    assert all(row['card']['id'] == 'quiet' for row in filtered['results'])
    assert filtered['selection']['cards'][1]['reason'] == 'missing-required-tag'
    excluded = client.post('/api/inspiration/preview', json={**body, 'filters': {'excluded_ids': ['quiet']}}).json()
    assert all(row['card']['id'] == 'loud' for row in excluded['results'])
    for filters in ({'tags': ['no-such-tag']}, {'excluded_ids': ['quiet', 'loud']}, {'excluded_ids': ['missing']}):
        assert client.post('/api/inspiration/preview', json={**body, 'filters': filters}).status_code == 400
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert client.get('/api/inspiration/draws').json() == client.get('/api/inspiration/decks').json() == []
    with client.app.state.database.connect() as connection:
        for table in ('generations', 'mechanic_opportunities', 'recipe_runs'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


@pytest.mark.parametrize('weight', [0, -1, True, '1', 0.0000001, 1.1234567, 1000001])
def test_invalid_weights_rejected_without_a_deck(client, weight):
    value = content()
    value['cards'][0]['weight'] = weight
    assert client.post('/api/inspiration/decks', json={'operation_id': uuid4().hex, 'name': 'Invalid', 'content': value}).status_code == 422
    assert client.get('/api/inspiration/decks').json() == []


@pytest.mark.parametrize('weight', [float('nan'), float('inf'), float('-inf')], ids=['nan', 'positive-inf', 'negative-inf'])
def test_nonfinite_weights_rejected(weight):
    with pytest.raises(ValidationError):
        Card.model_validate({**content()['cards'][0], 'weight': weight})


def test_card_and_pack_bounds_reject_incomplete_or_ambiguous_input(client):
    for cards in ([], [content()['cards'][0]] * 2, [dict(content()['cards'][0], id=f'card-{index}') for index in range(501)]):
        response = client.post('/api/inspiration/decks', json={'operation_id': uuid4().hex, 'name': 'Bad', 'content': {'cards': cards}})
        assert response.status_code == 422
    original = client.get('/api/inspiration/starters').json()[0]['document']
    documents = [{**original, 'version': 99}, {**original, 'version': True}, {**original, 'decks': original['decks'] * 33},
                 {**original, 'decks': original['decks'] * 2}]
    sources = [encode(document).encode() for document in documents] + [b'{"format":"a","format":"b"}', b'x' * (8 * 1024 * 1024 + 1)]
    for raw in sources:
        response = client.post('/api/inspiration/packs', json={'filename': 'bad.json', 'source_base64': base64.b64encode(raw).decode()})
        assert response.status_code == 400, response.text
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM inspiration_pack_sources').fetchone()[0] == 0


def test_recorded_draw_retries_restarts_and_keeps_the_selected_branch_unchanged(client, story, monkeypatch, tmp_path):
    calls = []
    def last_ticket(total):
        calls.append(total)
        return total - 1
    monkeypatch.setattr('server.inspiration.draws.randbelow', last_ticket)
    deck = create(client)
    head = append(client, story['branch_id'], 'Existing prose.', 0)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert not before['mechanics']['enabled']
    saved, body = draw(client, deck, branch_id=story['branch_id'], expected_revision=before['revision'])
    endpoint = f"/api/inspiration/versions/{deck['id']}/draws"
    assert saved['card']['id'] == 'loud' and saved['head_id'] == head
    assert client.post(endpoint, json=body).json() == saved and len(calls) == 1
    assert client.post(endpoint, json={**body, 'filters': {'tags': ['quiet']}}).status_code == 409
    assert client.post(endpoint, json={**body, 'operation_id': uuid4().hex, 'expected_revision': 0}).status_code == 409
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    other = client.post('/api/stories', json={'title': 'Other'}).json()
    assert client.get(f"/api/inspiration/draws?branch_id={other['branch_id']}").json() == []
    with TestClient(create_app(tmp_path / 'test.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as restarted:
        assert restarted.post(endpoint, json=body).json() == saved and len(calls) == 1
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            connection.execute('UPDATE inspiration_draws SET card_id=? WHERE id=?', ('quiet', saved['id']))


def test_explicit_card_handoff_freezes_generation_input_through_edits_and_restore(client, story, tmp_path):
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    make_profile(client, 'Writer', primary=True)
    deck = create(client)
    saved, _ = draw(client, deck, branch_id=story['branch_id'], expected_revision=0, filters={'tags': ['quiet']})
    direction = f"Inspiration from {deck['name']} v{deck['number']} · {saved['card']['title']}\n{saved['card']['text']}"
    assert provider.calls == []
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'profile_ids': [], 'direction': direction})
    assert response.status_code == 201, response.text
    generation = finished(client, response.json()['id'])
    assert len(provider.calls) == 1 and saved['card']['text'].strip() in str(provider.calls[0][2])
    assert decode(generation['snapshot']['content'])['direction'] == direction.strip()
    changed = client.post(f"/api/inspiration/decks/{deck['deck_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': deck['id'], 'name': 'Changed later',
        'content': {'cards': [{**deck['content']['cards'][0], 'text': 'Different future words.'}]}})
    assert changed.status_code == 201
    assert client.get(f"/api/generations/{generation['id']}").json()['snapshot'] == generation['snapshot']
    assert client.get(f"/api/inspiration/draws/{saved['id']}").json() == saved
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    _, archive = backup(client, story)
    with TestClient(create_app(tmp_path / 'handoff.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        staged = fresh.post('/api/archives/imports', json={'content': encode(archive)}).json()
        _, mapping = restore(fresh, staged)
        recovered = fresh.get(f"/api/generations/{mapping[generation['id']]}").json()
        assert decode(recovered['snapshot']['content'])['direction'] == direction.strip()
        assert recovered['candidates'][0]['output'] == generation['candidates'][0]['output']
        assert fresh.get(f"/api/inspiration/draws/{mapping[saved['id']]}").json()['card'] == saved['card']
    assert len(provider.calls) == 1


def test_pack_exact_sources_unknown_metadata_duplicates_and_explicit_updates(client):
    native = create(client)
    document = pack_source(client, [native])
    document['future_rules'] = {'deplete': True}
    document['decks'][0]['content']['cards'][0]['future_action'] = 'never execute'
    report, raw = stage(client, document)
    assert report['dependencies'] == [] and report['decks'][0]['duplicates'][0]['id'] == native['id']
    assert 'card.quiet.future_action' in report['decks'][0]['unsupported']
    assert client.get(f"/api/inspiration/packs/{report['id']}/original").content == raw
    skipped = import_pack(client, report)
    assert skipped['versions'] == [] and len(skipped['skipped']) == 1
    copied = import_pack(client, report, choices=[{'key': 'deck-1', 'duplicate_action': 'new'}])['versions'][0]
    assert copied['deck_id'] != native['deck_id']
    revised = import_pack(client, report, choices=[{'key': 'deck-1', 'target_deck_id': copied['deck_id'], 'expected_version_id': copied['id']}])['versions'][0]
    assert revised['number'] == 2 and revised['content'] == copied['content']
    stale = {'operation_id': uuid4().hex, 'source_sha256': report['source_sha256'], 'reviewed': True,
             'choices': [{'key': 'deck-1', 'target_deck_id': copied['deck_id'], 'expected_version_id': copied['id']}]}
    assert client.post(f"/api/inspiration/packs/{report['id']}/publish", json=stale).status_code == 409
    round_trip = pack_source(client, [copied])
    assert round_trip['decks'][0]['unsupported'] == copied['unsupported']
    assert client.get('/api/inspiration/draws').json() == []


def test_draw_history_keeps_older_results_accessible(client):
    from server.inspiration.draws import Draws
    from server.inspiration.models import Draw
    deck = create(client)
    service = Draws(client.app.state.database)
    saved = [service.create(deck['id'], Draw(operation_id=uuid4().hex)) for _ in range(101)]
    latest = client.get(f"/api/inspiration/draws?version_id={deck['id']}").json()
    older = client.get(f"/api/inspiration/draws?version_id={deck['id']}&offset=100").json()
    assert len(latest) == 100 and [item['id'] for item in older] == [saved[0]['id']]
    assert client.get('/api/inspiration/draws?offset=-1').status_code == 422
    assert client.get(f"/api/inspiration/draws/{saved[0]['id']}").json() == saved[0]


def test_pack_choices_are_atomic_and_identical_cards_dedupe_within_a_collection(client):
    native = create(client)
    document = pack_source(client, [native])
    document['decks'].append({**deepcopy(document['decks'][0]), 'key': 'another', 'name': 'Different name'})
    report, _ = stage(client, document)
    result = import_pack(client, report)
    assert len(result['skipped']) == 2 and not result['versions']
    body = {'operation_id': uuid4().hex, 'source_sha256': report['source_sha256'], 'reviewed': True,
            'choices': [{'key': 'deck-1', 'duplicate_action': 'new'}, {'key': 'another', 'target_deck_id': native['deck_id'], 'expected_version_id': 'stale'}]}
    assert client.post(f"/api/inspiration/packs/{report['id']}/publish", json=body).status_code == 409
    assert len(client.get('/api/inspiration/decks').json()) == 1
    document['decks'][0]['content']['cards'][0]['text'] = 'New shared content.'
    document['decks'][1]['content'] = deepcopy(document['decks'][0]['content'])
    next_report, _ = stage(client, document)
    result = import_pack(client, next_report)
    assert len(result['versions']) == len(result['skipped']) == 1


def test_pack_privacy_limits_and_starter_review_do_not_activate_anything(client):
    deck = create(client, unsupported={'endpoint': 'http://private.invalid', 'future': 'Keep me.'})
    document = pack_source(client, [deck])
    assert 'private.invalid' not in encode(document) and document['decks'][0]['unsupported']['future'] == 'Keep me.'
    document['api_key'] = 'DO_NOT_STORE'
    raw = base64.b64encode(encode(document).encode()).decode()
    response = client.post('/api/inspiration/packs', json={'filename': 'bad.json', 'source_base64': raw})
    assert response.status_code == 400
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM inspiration_pack_sources').fetchone()[0] == 0
    starters = client.get('/api/inspiration/starters').json()
    assert len(starters) == 3
    for item in starters:
        report, _ = stage(client, item['document'])
        assert len(report['decks'][0]['content']['cards']) == 5
    assert len(client.get('/api/inspiration/decks').json()) == 1 and client.get('/api/inspiration/draws').json() == []


def test_decks_draws_and_pack_sources_survive_story_and_workspace_restore(client, story, tmp_path):
    report, raw = stage(client, client.get('/api/inspiration/starters').json()[0]['document'])
    first = import_pack(client, report)['versions'][0]
    saved, _ = draw(client, first, branch_id=story['branch_id'], expected_revision=0)
    later = client.post(f"/api/inspiration/decks/{first['deck_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': first['id'], 'name': 'Later version', 'content': content()})
    assert later.status_code == 201
    create(client, name='Unrelated Library deck')
    assert client.get(f"/api/inspiration/draws/{saved['id']}").json() == saved
    _, scoped = backup(client, story)
    assert len(scoped['data']['inspiration_decks']) == 1 and len(scoped['data']['inspiration_versions']) == 2
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        staged = fresh.post('/api/archives/imports', json={'content': encode(scoped)}).json()
        _, mapping = restore(fresh, staged)
        restored = fresh.get(f"/api/inspiration/draws/{mapping[saved['id']]}").json()
        assert restored['selection'] == saved['selection'] and restored['card'] == saved['card']
        assert restored['version_id'] == mapping[first['id']] and restored['ticket'] == saved['ticket']
        assert restored['branch_id'] == mapping[story['branch_id']]
        assert fresh.get(f"/api/inspiration/packs/{mapping[report['id']]}/original").content == raw
        _, exported = backup(fresh)
        assert exported['version'] == ARCHIVE_VERSION
        assert len(exported['data']['inspiration_draws']) == 1
    _, workspace = backup(client)
    assert len(workspace['data']['inspiration_decks']) == 2


def test_portable_collection_imports_selected_versions_into_a_fresh_workspace(client, tmp_path):
    first = create(client)
    second = create(client, name='A different deck', content={'cards': [{'id': 'one', 'title': 'One', 'text': 'A separate suggestion.', 'weight': 2}]})
    document = pack_source(client, [second, first])
    assert list(document) == ['format', 'version', 'name', 'description', 'decks']
    with TestClient(create_app(tmp_path / 'portable.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        report, raw = stage(fresh, document)
        assert all(not item['duplicates'] for item in report['decks'])
        imported = import_pack(fresh, report)['versions']
        assert [row['content'] for row in imported] == [second['content'], first['content']]
        assert all(row['id'] not in {first['id'], second['id']} for row in imported)
        assert pack_source(fresh, imported) == document
        assert fresh.get('/api/stories').json() == fresh.get('/api/inspiration/draws').json() == []
        assert fresh.get(f"/api/inspiration/packs/{report['id']}/original").content == raw


@pytest.mark.parametrize('change', ['ticket', 'card', 'odds', 'filters', 'head', 'source'])
def test_archive_rejects_tampered_decks_and_draw_receipts(client, story, change):
    report, _ = stage(client, client.get('/api/inspiration/starters').json()[0]['document'])
    deck = import_pack(client, report)['versions'][0]
    draw(client, deck)
    _, document = backup(client)
    row = document['data']['inspiration_draws'][0]
    if change == 'ticket':
        row['ticket'] = -1
    elif change == 'card':
        row['card_id'] = 'invented'
    elif change in {'odds', 'filters'}:
        selection = decode(row['selection'])
        if change == 'odds':
            selection['cards'][0]['probability']['numerator'] += 1
        else:
            selection['filters']['excluded_ids'] = ['invented']
        row['selection'] = encode(selection)
    elif change == 'head':
        node = append(client, story['branch_id'], 'Private prose.', 0)
        _, document = backup(client)
        document['data']['inspiration_draws'][0]['head_id'] = node
    else:
        document['data']['inspiration_pack_sources'][0]['source_sha256'] = '0' * 64
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_format_53_upgrades_without_inventing_decks_or_draws(client):
    _, document = backup(client)
    document['version'] = 53
    document['data'] = {key: value for key, value in document['data'].items() if key in V53_TABLES}
    parsed = parse_archive(encode(document))
    assert parsed['version'] == ARCHIVE_VERSION
    assert all(parsed['data'][table] == [] for table in INSPIRATION_TABLES)


def test_archive_rejects_draw_reassigned_to_a_different_telling_in_the_same_story(client, story):
    deck = create(client)
    first = append(client, story['branch_id'], 'Original opening.', 0)
    append(client, story['branch_id'], 'Selected source boundary.', 1)
    draw(client, deck, branch_id=story['branch_id'], expected_revision=2)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 2, 'node_id': first,
        'name': 'A different telling', 'replacement': 'An alternate opening.'}).json()
    append(client, story['branch_id'], 'Later prose still permits the earlier draw.', 2)
    _, document = backup(client, story)
    parse_archive(encode(document))
    document['data']['inspiration_draws'][0]['branch_id'] = fork['branch_id']
    with pytest.raises(DomainError, match='outside its recorded Story path'):
        parse_archive(encode(document))
