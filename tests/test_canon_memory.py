import base64
import json
from copy import deepcopy
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest

from server.character_content import narrative_asset
from server.database import decode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.library_formats.brain_pack import validate_pack
from server.memory.canon_compiler import compile_overview, source_digest
from server.memory.packet import assemble_memory, token_estimate
from tests.test_archives import backup, restore
from tests.test_context_inspector import database_dump, preview, read_section
from tests.test_generations import DraftProvider, finished
from tests.test_library import adoption_request, with_book
from tests.test_library_imports import publish_body, publish_import, stage
from tests.test_memory import fixture_context, profiles, small_profile


def brain_pack():
    return {'schema': 'sgc-brain/1', 'id': 'glass-city', 'name': 'The glass city',
            'description': 'Two reference passages.', 'version': '1', 'built_at': '2026-09-17T12:00:00Z',
            'source': {'tool': 'atlantis', 'schema': 'atlantis-salience-v1', 'stub': False},
            'unknown_extension': {'url': 'https://never-fetch.invalid/content'},
            'chunks': [
                {'id': '../untrusted-path', 'title': 'The conservatory',
                 'text': 'Moon orchids close when exposed to iron dust. Their pollen opens the east vault.',
                 'summary': 'A botanical vault mechanism.', 'topics': ['botany'],
                 'aliases': ['silver blossom', 'night flower'], 'source': {'file': '../../outside.md',
                 'doc': 'plants', 'position': 1}, 'tokens': 30},
                {'id': 'transport', 'title': 'The river ferry', 'text': 'The river ferry takes copper coins.',
                 'summary': '', 'topics': ['transport'], 'aliases': [],
                 'source': {'file': 'ferry.md', 'doc': 'transport', 'position': 2}, 'tokens': 10},
            ]}


def imported_book(client):
    pack = brain_pack()
    raw = b'\xef\xbb\xbf' + json.dumps(pack, ensure_ascii=False, indent=3).encode()
    staged = stage(client, raw, 'glass-city.json')
    response = publish_import(client, staged)
    assert response.status_code == 201, response.text
    return response.json()['versions'][0], staged, raw


def attached(version, enabled=True):
    return {'asset_id': version['asset_id'], 'version_id': version['id'], 'kind': 'lorebook',
            'enabled': enabled, 'priority': 0, 'version': version}


def test_sgc_review_preserves_original_json_and_maps_prose_to_editable_markdown(client):
    raw = json.dumps(brain_pack(), ensure_ascii=False, indent=2).encode()
    staged = stage(client, raw, 'glass-city.json')
    assert staged['format'] == 'sgc-brain'
    assert client.get('/api/library').json() == []
    assert client.get(f"/api/library-imports/{staged['id']}/original").content == raw
    body = publish_body(staged)
    body['reviewed_compatibility'] = False
    assert publish_import(client, staged, body).status_code == 400
    body['reviewed_compatibility'] = True
    body['choices'][0]['content']['text'] += '\nAn author addition.\n'
    result = publish_import(client, staged, body)
    assert result.status_code == 201, result.text
    book = result.json()['versions'][0]
    assert book['content']['text'].endswith('An author addition.\n')
    assert book['content']['canon_recall']['mode'] == 'relevant'
    assert 'canon_recall' not in narrative_asset(attached(book))['version']['content']
    package = client.get(f"/api/library-imports/{staged['id']}/package")
    with ZipFile(BytesIO(package.content)) as archive:
        assert archive.read('source.json') == raw
        assert all('..' not in name.split('/') for name in archive.namelist())
        converted = archive.read('converted/canon/chunks/00001.md').decode()
        assert '../../outside.md' in converted  # A preserved field, never a filesystem path.
    assert client.get('/api/stories').json() == []


def test_compiler_searches_imported_aliases_without_sending_cues_as_world_facts(client):
    book, _staged, _raw = imported_book(client)
    before = database_dump(client)
    response = client.post('/api/canon/compile-preview', json={
        'name': book['name'], 'content': book['content'], 'query': 'silver blossom'})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['active_cues'] == 2 and report['stale_cues'] == 0
    assert len(report['items']) == 1
    excerpt = report['items'][0]
    assert 'Moon orchids' in excerpt['text'] and 'silver blossom' not in excerpt['text']
    assert excerpt['search_cues']['aliases'] == ['silver blossom', 'night flower']
    assert book['content']['text'][excerpt['start']:excerpt['end']] == excerpt['text']
    assert database_dump(client) == before


def test_edited_source_invalidates_only_its_cues_without_rewriting_human_text(client):
    book, _staged, _raw = imported_book(client)
    content = deepcopy(book['content'])
    content['text'] = content['text'].replace('iron', 'gold')
    compiled, report = compile_overview('version:test', book['name'], content)
    assert report['stale_cues'] == 1 and report['active_cues'] == 1
    assert not any('silver blossom' in chunk.aliases for chunk in compiled)
    assert 'gold dust' in ''.join(chunk.text for chunk in compiled)
    response = client.post('/api/canon/compile-preview', json={'name': book['name'], 'content': content, 'query': 'silver blossom'})
    assert response.json()['items'] == []
    assert content['canon_recall']['cues'] == book['content']['canon_recall']['cues']


def test_long_writer_retrieves_canon_separately_with_exact_version_receipts(client):
    book, _staged, _raw = imported_book(client)
    context = fixture_context()
    context['direction'] = 'Inspect the silver blossom.'
    context['library'] = [narrative_asset(attached(book))]
    original = deepcopy(context)
    packet, receipt = assemble_memory(context, 'Write.', profiles(8192), canon_assets=[attached(book)])
    assert context == original
    assert 'text' not in packet['library'][0]['version']['content']
    assert any('Moon orchids' in item['text'] for item in packet['recalled_canon'])
    assert all(item['source_id'] == f"version:{book['id']}" for item in packet['recalled_canon'])
    assert receipt['canon']['collections'][0]['version_id'] == book['id']
    assert receipt['canon']['collections'][0]['selected_chunks'] > 0
    assert 'summary' not in packet['recalled_canon'][0] and 'aliases' not in packet['recalled_canon'][0]
    assert token_estimate('Write.', packet) + receipt['overhead_margin'] <= 8192 - 512
    assert assemble_memory(context, 'Write.', profiles(8192, 16384), canon_assets=[attached(book)]) == (packet, receipt)


def test_wrong_version_disabled_collection_and_rule_entries_never_enter_overview_recall(client):
    book, _staged, _raw = imported_book(client)
    disabled = deepcopy(book)
    disabled.update(id='disabled', asset_id='disabled-asset')
    disabled['content']['text'] = 'DISABLED silver blossom secret.'
    future = deepcopy(book)
    future['id'] = 'future-version'
    future['content']['text'] = 'FUTURE silver blossom secret.'
    book['content']['lore_definition'] = {'entries': [{'id': 'off', 'title': 'Hidden',
        'text': 'HIDDEN_ENTRY silver blossom secret.', 'enabled': False, 'activation': 'always'}]}
    context = fixture_context()
    context.update(direction='silver blossom secret', library=[narrative_asset(attached(book))])
    packet, receipt = assemble_memory(context, 'Write.', profiles(8192),
        canon_assets=[attached(future), attached(disabled, False), attached(book)])
    encoded = json.dumps(packet)
    assert all(marker not in encoded for marker in ('DISABLED', 'FUTURE', 'HIDDEN_ENTRY'))
    assert len(receipt['canon']['collections']) == 1
    assert {item['source_id'] for item in packet['recalled_canon']} == {f"version:{book['id']}"}


def test_complete_overview_policy_and_full_history_remain_complete(client):
    book, _staged, _raw = imported_book(client)
    book['content']['canon_recall']['mode'] = 'full'
    context = fixture_context()
    context['library'] = [narrative_asset(attached(book))]
    packet, receipt = assemble_memory(context, 'Write.', profiles(8192), canon_assets=[attached(book)])
    assert packet['library'][0]['version']['content']['text'] == book['content']['text']
    assert 'canon' not in receipt
    context['story']['settings']['memory']['mode'] = 'full'
    book['content']['canon_recall']['mode'] = 'relevant'
    packet, receipt = assemble_memory(context, 'Write.', profiles(8192), canon_assets=[attached(book)])
    assert packet is context and receipt is None


def test_native_export_requires_review_of_selected_rules_and_is_read_only(client):
    body = {'kind': 'lorebook', 'name': 'Native world', 'content': {'text': '# Harbor\n\nThe harbor is shallow.',
        'lore_definition': {'entries': [{'id': 'secret', 'title': 'The sealed gate', 'text': 'SEALED_GATE_PROSE',
                                      'enabled': False, 'activation': 'keywords', 'keywords': ['password']} ]}}}
    book = client.post('/api/library', json=body).json()
    endpoint = f"/api/versions/{book['id']}/brain-pack"
    before = database_dump(client)
    overview = client.post(endpoint, json={})
    assert overview.status_code == 200, overview.text
    assert validate_pack(overview.json()).source.stub
    assert 'SEALED_GATE_PROSE' not in overview.text
    assert client.post(endpoint, json={'entry_ids': ['secret']}).status_code == 400
    full = client.post(endpoint, json={'entry_ids': ['secret'], 'reviewed_rules': True})
    assert full.status_code == 200 and 'SEALED_GATE_PROSE' in full.text
    assert full.json() == client.post(endpoint, json={'entry_ids': ['secret'], 'reviewed_rules': True}).json()
    assert database_dump(client) == before
    staged = stage(client, full.content, 'export.json')
    assert staged['format'] == 'sgc-brain'


def test_pack_reimport_publishes_new_version_keeps_old_story_pin_and_archive_provenance(client):
    book, original, raw = imported_book(client)
    story = with_book(client, book, 'Pinned Canon')
    pack = brain_pack()
    pack['chunks'][0]['text'] = 'Moon orchids thrive in iron dust in this revised world.'
    second = stage(client, json.dumps(pack).encode(), 'updated.json')
    body = publish_body(second)
    body['choices'][0].update(target_asset_id=book['asset_id'], expected_version_id=book['id'])
    result = publish_import(client, second, body)
    assert result.status_code == 201, result.text
    revised = result.json()['versions'][0]
    assert revised['number'] == 2
    assert client.get(f"/api/stories/{story['story_id']}").json()['attachments'][0]['version_id'] == book['id']
    archive, _document = backup(client)
    _, mapping = restore(client, archive)
    assert client.get(f"/api/library-imports/{mapping[original['id']]}/original").content == raw
    restored = client.get('/api/library').json()
    restored_book = next(item for item in restored if item['id'] == mapping[revised['id']])
    assert restored_book['content'] == revised['content']
    endpoint = f"/api/versions/{revised['id']}/adoption"
    targets = client.get(endpoint).json()
    assert client.post(endpoint, json=adoption_request(targets)).status_code == 200
    assert client.get(f"/api/stories/{story['story_id']}").json()['attachments'][0]['version_id'] == revised['id']


def test_writer_preview_canon_matches_saved_request_and_retry_inputs(client):
    book, _staged, _raw = imported_book(client)
    profile = small_profile(client, limit=8192)
    texts = fixture_context()['history']
    story = client.post('/api/stories', json={'title': 'Canon writer', 'settings': {'memory': {'mode': 'long'}},
        'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
    from tests.test_history import append
    for index, node in enumerate(texts):
        append(client, story['branch_id'], node['text'], index)
    report, request = preview(client, story, expected_revision=len(texts), profile_ids=[profile['profile_id']], direction='silver blossom')
    section = read_section(client, story, report, request, 'recalled_canon', view='readable')
    assert section.status_code == 200 and 'Moon orchids' in section.json()['text']
    client.app.state.runner.provider = DraftProvider()
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={**request, 'operation_id': uuid4().hex})
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    assert run['snapshot']['memory']['canon'] == report['memory']['canon']
    assert json.loads(run['snapshot']['content'])['recalled_canon']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    with client.app.state.database.connect() as connection:
        restored = decode(one(connection, 'SELECT snapshot FROM generations WHERE id=?', (mapping[run['id']],))['snapshot'])
    assert restored['content'] == run['snapshot']['content']
    assert restored['memory']['canon'] == report['memory']['canon']


@pytest.mark.parametrize('mutation', ['duplicate', 'alias_type', 'too_long', 'nonfinite', 'no_chunks', 'new_schema'])
def test_malformed_sgc_packs_fail_before_publication(client, mutation):
    pack = brain_pack()
    if mutation == 'duplicate':
        pack['chunks'].append(pack['chunks'][0])
    elif mutation == 'alias_type':
        pack['chunks'][0]['aliases'] = {'a': 'b'}
    elif mutation == 'too_long':
        pack['chunks'][0]['text'] = '🌙' * 4001
    elif mutation == 'nonfinite':
        pack['chunks'][0]['tokens'] = float('nan')
    elif mutation == 'new_schema':
        pack['schema'] = 'sgc-brain/2'
    else:
        pack['chunks'] = []
    response = client.post('/api/library-imports', json={
        'filename': 'bad.json', 'source_base64': base64.b64encode(json.dumps(pack).encode()).decode()})
    assert response.status_code == 400, response.text
    assert client.get('/api/library').json() == []


def test_native_canon_cue_validation_and_read_only_preview_paging(client):
    content = {'text': ''.join(f'## Chapter {index}\n\nA quiet room.\n\n' for index in range(30)),
               'canon_recall': {'mode': 'relevant'}}
    first = client.post('/api/canon/compile-preview', json={'content': content}).json()
    assert first['chunks'] == 30 and len(first['items']) == 12 and first['next_offset'] == 12
    second = client.post('/api/canon/compile-preview', json={'content': content, 'offset': 12}).json()
    assert not {item['id'] for item in first['items']} & {item['id'] for item in second['items']}
    cue = {'start': 0, 'end': 8, 'sha256': source_digest(content['text'][:8])}
    content['canon_recall']['cues'] = [cue, cue]
    response = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Invalid', 'content': content})
    assert response.status_code == 400


def test_long_memory_preserves_native_entry_positions_and_reuses_recorded_chance(client, monkeypatch):
    from tests.test_history import append
    from tests.test_lore_runtime import fixture_story, receipt
    from tests.test_mechanics import configure, prepare

    _, story = fixture_story(client)
    small_profile(client, limit=8192)
    configure(client, story, narrative_push=False, encounter=False, handling=False)
    current = client.get(f"/api/stories/{story['story_id']}").json()
    response = client.put(f"/api/stories/{story['story_id']}", json={
        'expected_revision': current['revision'], 'title': current['title'], 'premise': '',
        'settings': {**current['settings'], 'memory': {'mode': 'long'}}})
    assert response.status_code == 200, response.text
    history = fixture_context()['history']
    for index, node in enumerate(history):
        append(client, story['branch_id'], node['text'], index)
    prepared = prepare(client, story['branch_id'], revision=len(history), beat={'label': 'Boundary', 'family': 'none'})
    saved = receipt(client, prepared)

    def forbidden(*_args):
        pytest.fail('Canon or story retrieval must not draw chance')

    monkeypatch.setattr('server.lore.engine.Draws.die', forbidden)
    before = database_dump(client)
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=len(history))
    with client.app.state.database.connect() as connection:
        snapshot, _ = generation_snapshot(connection, story['branch_id'], body)
    packet = decode(snapshot['content'])
    assert list(packet)[0] == 'lore_header'
    assert list(packet)[-3:] == ['lore_recent', 'direction', 'lore_tail']
    assert 'EXCLUDED_ENTRY_PROSE' not in snapshot['content']
    assert snapshot['lore'] == saved['lore']
    assert packet['lore_tail'][0]['title'].endswith('Detail')
    assert database_dump(client) == before


def test_sgc_pack_disguised_as_png_card_is_rejected(client):
    from tests.test_artwork import insert_text, png

    raw = insert_text(png(), b'chara'+bytes([0])+base64.b64encode(json.dumps(brain_pack()).encode()))
    response = client.post('/api/library-imports', json={
        'filename': 'not-a-card.png', 'source_base64': base64.b64encode(raw).decode()})
    assert response.status_code == 400
    assert 'SGC packs as JSON' in response.json()['detail']


def test_small_profile_can_fit_one_relevant_full_sized_canon_excerpt():
    text = '# Moon orchard'+chr(10)+(('The orchid pollen opens the vault. ')*65)
    book = {'id': 'large', 'asset_id': 'large-asset', 'name': 'Orchard', 'number': 1,
            'content': {'text': text, 'canon_recall': {'mode': 'relevant'}}}
    context = fixture_context()
    context['direction'] = 'Orchid pollen vault.'
    context['library'] = [narrative_asset(attached(book))]
    packet, receipt = assemble_memory(context, 'Write.', profiles(4096), canon_assets=[attached(book)])
    assert packet['recalled_canon'] and len(packet['recalled_canon'][0]['text']) > 2000
    assert token_estimate('Write.', packet) + receipt['overhead_margin'] <= 4096 - 512
