import json
import math
from uuid import uuid4

import pytest

from server.assessment.context import assessment_snapshot
from server.database import one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from tests.test_assessments import setup_assessment
from tests.test_background import prepared
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_library import create_book, publish, with_book
from tests.test_profiles import make_profile


def preview(client, story, **values):
    body = {'expected_revision': 0, **values}
    response = client.post(f"/api/branches/{story['branch_id']}/context-preview", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def read_section(client, story, report, body, section, offset=0, view='exact'):
    return client.post(f"/api/branches/{story['branch_id']}/context-preview/section", json={
        **body, 'fingerprint': report['fingerprint'], 'section': section, 'offset': offset, 'view': view})


def database_dump(client):
    with client.app.state.database.connect() as connection:
        return '\n'.join(connection.iterdump())


def test_preview_and_pages_are_read_only_and_match_actual_provider_input(client, story, monkeypatch):
    make_profile(client, 'Writer', primary=True)
    append(client, story['branch_id'], 'Rain on the quay. 雨 🌧', 0)
    before = database_dump(client)
    monkeypatch.setattr('server.assessment.context.secrets.token_hex', lambda *_: pytest.fail('Preview drew randomness'))
    report, body = preview(client, story, expected_revision=1, direction='Keep the rain gentle.')
    texts = [read_section(client, story, report, body, section['key']).json()['text'] for section in report['sections']]
    assert database_dump(client) == before
    assert sum(section['bytes'] for section in report['sections']) == len(''.join(texts).encode('utf-8'))
    estimated = math.ceil(len(''.join(texts).encode('utf-8')) / 3)
    assert sum(section['estimated_tokens'] for section in report['sections']) == estimated
    assert report['budgets'][0]['estimated_input_tokens'] == estimated
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    run = client.post(f"/api/branches/{story['branch_id']}/generations", json={**body, 'operation_id': uuid4().hex}).json()
    frozen = finished(client, run['id'])['snapshot']
    assert (texts[0], ''.join(texts[1:])) == provider.calls[0][1:]
    assert frozen['estimated_input_tokens'] == estimated


def test_over_budget_comparison_is_inspectable_but_generation_is_still_blocked(client, story):
    small = client.post('/api/profiles', json={'name': 'Small', 'config': {
        'provider': 'local', 'model': 'small', 'context_tokens': 1024, 'max_output_tokens': 1000}}).json()
    large = make_profile(client, 'Large')
    report, body = preview(client, story, profile_ids=[small['profile_id'], large['profile_id']])
    first, second = report['budgets']
    assert not first['fits'] and first['remaining_tokens'] < 0
    assert second['fits'] and first['estimated_input_tokens'] == second['estimated_input_tokens']
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={**body, 'operation_id': uuid4().hex})
    assert response.status_code == 409
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []


def test_library_uses_pinned_markdown_version_even_after_publication(client):
    make_profile(client, 'Writer', primary=True)
    book = create_book(client)
    story = with_book(client, book, 'Old weather')
    publish(client, book)
    report, body = preview(client, story)
    section = read_section(client, story, report, body, 'library').json()
    assert 'Rain every day.' in section['text'] and 'A dry season.' not in section['text']
    assert book['id'] in section['sources'][0]
    assert 'v1' in section['sources'][0]
    readable = read_section(client, story, report, body, 'library', view='readable').json()['text']
    assert 'Rain every day.' in readable and 'created_at' not in readable
    assert 'The city · lorebook · v1' in readable and book['id'] in readable


def test_preview_does_not_expose_author_notes_greetings_or_artwork(client):
    make_profile(client, 'Writer', primary=True)
    asset = client.post('/api/library', json={'kind': 'character', 'name': 'Mara', 'content': {
        'text': 'Included characterization.', 'author_notes': 'AUTHOR-ONLY',
        'greetings': [{'id': 'hello', 'label': 'Hello', 'text': 'UNSELECTED-GREETING'}]}}).json()
    story = with_book(client, asset, 'An unstarted tale')
    report, body = preview(client, story)
    section = read_section(client, story, report, body, 'library').json()['text']
    assert 'Included characterization.' in section
    assert 'AUTHOR-ONLY' not in section and 'UNSELECTED-GREETING' not in section


def test_character_pages_reassemble_exactly_without_truncation(client, story):
    make_profile(client, 'Writer', primary=True)
    text = 'A café in the rain. 雨' * 700
    append(client, story['branch_id'], text, 0)
    report, body = preview(client, story, expected_revision=1)
    first = read_section(client, story, report, body, 'history').json()
    second = read_section(client, story, report, body, 'history', first['next_offset']).json()
    combined = first['text'] + second['text']
    assert len(first['text']) == 8000 and second['next_offset'] is None
    assert text in combined and len(combined) == first['total_characters']
    assert len(combined.encode('utf-8')) == next(s['bytes'] for s in report['sections'] if s['key'] == 'history')


def test_stale_prompt_or_branch_cannot_mix_section_pages(client, story):
    make_profile(client, 'Writer', primary=True)
    report, body = preview(client, story)
    prompt = next(item for item in client.get('/api/prompts').json() if item['key'] == 'writer')
    client.put('/api/prompts/writer', json={'expected_version_id': prompt['id'], 'template': 'Changed instructions.'})
    assert read_section(client, story, report, body, 'prompt').status_code == 409
    refreshed, body = preview(client, story)
    assert refreshed['fingerprint'] != report['fingerprint']
    append(client, story['branch_id'], 'A new moment.', 0)
    assert read_section(client, story, refreshed, body, 'history').status_code == 409


def test_profile_version_change_invalidates_old_preview(client, story):
    profile = make_profile(client, 'Writer', primary=True)
    report, body = preview(client, story)
    client.put(f"/api/profiles/{profile['profile_id']}", json={'expected_version_id': profile['id'],
        'name': 'Writer revised', 'config': {**profile['config'], 'max_output_tokens': 1500}})
    assert read_section(client, story, report, body, 'story').status_code == 409


def test_assessment_preview_uses_real_request_budget_without_seed_or_jobs(client, story, monkeypatch):
    setup_assessment(client, story)
    with client.app.state.database.connect() as connection:
        body = GenerateRequest(operation_id=uuid4().hex, expected_revision=1)
        writer, profiles = generation_snapshot(connection, story['branch_id'], body)
        saved_story = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        expected = assessment_snapshot(connection, saved_story, writer, profiles, body)['jobs'][0]
    before = database_dump(client)
    monkeypatch.setattr('server.assessment.context.secrets.token_hex', lambda *_: pytest.fail('Preview created seed'))
    report, _ = preview(client, story, expected_revision=1)
    assert report['assessment']['status'] == 'new'
    assert report['assessment']['budgets'][0]['estimated_input_tokens'] == expected['estimated_input_tokens']
    assert database_dump(client) == before
    assert client.app.state.assessment_runner.provider.calls == []
    skipped, _ = preview(client, story, expected_revision=1, assess_beat=False)
    assert skipped['assessment']['status'] == 'none'


def test_summary_excludes_source_text_and_credentials(client, story):
    make_profile(client, 'Writer', primary=True)
    append(client, story['branch_id'], 'PRIVATE-PROSE-MARKER', 0)
    report, _ = preview(client, story, expected_revision=1)
    assert 'PRIVATE-PROSE-MARKER' not in json.dumps(report)
    assert 'credential_ref' not in json.dumps(report)
    assert report['coverage']['messages'] == 1


def test_missing_profile_and_invalid_section_have_actionable_errors(client, story):
    endpoint = f"/api/branches/{story['branch_id']}/context-preview"
    missing = client.post(endpoint, json={'expected_revision': 0})
    assert missing.status_code == 409 and 'Primary Writer' in missing.json()['detail']
    profile = make_profile(client, 'Writer', primary=True)
    duplicate = client.post(endpoint, json={'expected_revision': 0, 'profile_ids': [profile['profile_id']] * 2})
    assert duplicate.status_code == 400
    report, body = preview(client, story)
    assert read_section(client, story, report, body, 'unknown').status_code == 404
    assert read_section(client, story, report, body, 'story', 999999).status_code == 400


def test_historical_fork_excludes_abandoned_future(client, story):
    make_profile(client, 'Writer', primary=True)
    first = append(client, story['branch_id'], 'The ferry arrives.', 0)
    append(client, story['branch_id'], 'FUTURE-REVELATION', 1)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 2, 'node_id': first, 'name': 'Another tide'}).json()
    branch = client.get(f"/api/branches/{fork['branch_id']}").json()
    report, body = preview(client, fork, expected_revision=branch['revision'])
    section = read_section(client, fork, report, body, 'history').json()
    assert 'The ferry arrives.' in section['text'] and 'FUTURE-REVELATION' not in section['text']
    assert report['coverage']['messages'] == 1


def test_private_background_is_counted_but_only_revealed_on_section_read(client, story, monkeypatch):
    make_profile(client, 'Writer', primary=True)
    prepared(client, story, day=12, horizon=7, origin='Arrival at the station')
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    before = database_dump(client)
    monkeypatch.setattr('server.assessment.context.secrets.token_hex', lambda *_: pytest.fail('Preview drew randomness'))
    report, body = preview(client, story, expected_revision=revision)
    summary = next(item for item in report['sections'] if item['key'] == 'private_background')
    assert summary['bytes'] > 0 and 'text' not in summary
    section = read_section(client, story, report, body, 'private_background').json()
    assert len(section['text'].encode('utf-8')) == summary['bytes']
    assert database_dump(client) == before
