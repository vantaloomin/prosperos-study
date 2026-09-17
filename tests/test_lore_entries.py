import json
from copy import deepcopy
from pathlib import Path

import pytest

from server.archives.validate import parse_archive
from server.character_content import narrative_asset
from server.database import decode, encode
from server.errors import DomainError
from server.library_formats.markdown import document
from server.lore.documents import entry_markdown
from server.lore.engine import select_lore
from server.lore.models import LoreDefinition, LoreEntry
from tests.archive_legacy import remove_authoring
from tests.test_archives import backup, restore
from tests.test_card_markdown import card
from tests.test_library import with_book
from tests.test_library_imports import publish_import, stage


def entry(entry_id='harbor', **changes):
    return LoreEntry(id=entry_id, title=entry_id.title(), text='\n# Quiet water\r\n\r\nThe quay is closed. 🌊\n\n',
                     activation='always', **changes).model_dump()


def make_book(client, entries=None):
    content = {'text': 'The tide follows the moon.', 'lore_definition': {'entries': entries or [entry()]}, 'unknown': {'preserved': True}}
    response = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Harbor rules', 'content': content})
    assert response.status_code == 201, response.text
    return response.json()


def files(client, book):
    response = client.get(f"/api/versions/{book['id']}/entry-files")
    assert response.status_code == 200, response.text
    return response.json()


def publish(client, book, content, hashes=None):
    return client.post(f"/api/library/{book['asset_id']}/versions", json={
        'expected_version_id': book['id'], 'expected_entry_hashes': hashes or {}, 'name': book['name'], 'content': content})


def test_entry_files_publication_external_metadata_and_pins(client, monkeypatch):
    first = make_book(client)
    story = with_book(client, first, 'Pinned harbor')
    source = files(client, first)[0]
    path = Path(source['file_path'])
    expected = first['content']['lore_documents']['harbor']
    assert path.read_bytes() == expected.encode() and first['content']['unknown'] == {'preserved': True}
    changed = LoreEntry.model_validate({**first['content']['lore_definition']['entries'][0], 'title': 'Tide gate', 'text': '\nNew prose.\r\n\n', 'enabled': False})
    external = entry_markdown(changed).replace('  "kind"', '    "kind"')
    path.write_bytes(external.encode())
    assert publish(client, first, first['content']).status_code == 409
    proposal = client.get(f"/api/versions/{first['id']}/entry-file", params={'entry_id': 'harbor'}).json()
    next_content = {**first['content'], 'lore_definition': {'entries': [proposal['entry']]}, 'lore_documents': {'harbor': external}}
    second_response = publish(client, first, next_content, {'harbor': proposal['sha256']})
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert second['content']['lore_documents']['harbor'] == external
    assert Path(files(client, second)[0]['file_path']).read_bytes() == path.read_bytes()
    assert client.get(f"/api/versions/{first['id']}/entry-download", params={'entry_id': 'harbor'}).content == expected.encode()
    monkeypatch.setattr('server.lore.files.read_markdown', lambda _path: pytest.fail('History scanned entry files'))
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['attachments'][0]['version_id'] == first['id']
    assert 'lore_definition' not in narrative_asset(branch['attachments'][0])['version']['content']
    assert 'lore_documents' not in narrative_asset(branch['attachments'][0])['version']['content']


def test_entry_conflict_after_review_and_failed_write_are_atomic(client, monkeypatch):
    book = make_book(client)
    original = files(client, book)[0]
    path = Path(original['file_path'])
    path.write_text('Unreviewed file', encoding='utf-8')
    reviewed = files(client, book)[0]
    path.write_text('Changed again', encoding='utf-8')
    assert publish(client, book, book['content'], {'harbor': reviewed['sha256']}).status_code == 409
    current = files(client, book)[0]
    def fail(*_args):
        raise OSError('Simulated full disk')
    monkeypatch.setattr('server.library_formats.files.exclusive_write', fail)
    assert publish(client, book, book['content'], {'harbor': current['sha256']}).status_code == 503
    assert client.get('/api/library').json()[0]['id'] == book['id']
    assert path.read_text(encoding='utf-8') == 'Changed again'


def test_entry_recovery_identity_and_invalid_external_header(client):
    book = make_book(client)
    source = files(client, book)[0]
    path = Path(source['file_path'])
    path.unlink()
    endpoint = f"/api/versions/{book['id']}/entry-recover?entry_id=harbor"
    body = {'version_id': book['id'], 'target': 'working', 'expected_hash': None}
    assert client.post(endpoint, json={**body, 'version_id': 'another'}).status_code == 400
    assert client.post(endpoint, json=body).status_code == 200
    assert client.post(endpoint, json=body).status_code == 409
    snapshot = path.parents[4] / 'objects' / (source['published_sha256'] + '.md')
    assert snapshot.exists()
    snapshot.write_bytes(b'\xff\x00damaged')
    damaged = files(client, book)[0]
    response = client.post(endpoint, json={**body, 'target': 'published', 'expected_hash': damaged['snapshot_hash']})
    assert response.status_code == 200, response.text
    assert Path(response.json()['retained_file']).read_bytes() == b'\xff\x00damaged'
    path.write_text(document({'kind': 'native-lore-entry', 'entry': {'id': '../other', 'title': 'Other', 'activation': 'always'}}, 'Changed ID'), encoding='utf-8')
    assert client.get(f"/api/versions/{book['id']}/entry-file?entry_id=harbor").status_code == 400


def test_entry_archives_preserve_missing_and_edited_files_and_exact_source(client):
    book = make_book(client, [entry(), entry('island')])
    current = files(client, book)
    Path(current[0]['file_path']).write_bytes(b'\nUnpublished Markdown\r\n')
    Path(current[1]['file_path']).unlink()
    archive, exported = backup(client)
    assert exported['version'] == 19
    assert exported['lore_drafts'][book['id']] == {'harbor': '\nUnpublished Markdown\r\n', 'island': None}
    _result, mapping = restore(client, archive)
    recovered = next(item for item in client.get('/api/library').json() if item['id'] == mapping[book['id']])
    recovered_files = files(client, recovered)
    assert recovered['content'] == book['content']
    assert Path(recovered_files[0]['file_path']).read_bytes() == b'\nUnpublished Markdown\r\n'
    assert recovered_files[1]['missing']
    broken = deepcopy(exported)
    content = decode(broken['data']['asset_versions'][0]['content'])
    content['lore_documents']['harbor'] += 'forged'
    broken['data']['asset_versions'][0]['content'] = encode(content)
    with pytest.raises(DomainError):
        parse_archive(json.dumps(broken))
    legacy = deepcopy(exported)
    remove_authoring(legacy)
    legacy['version'] = 13
    legacy.pop('lore_drafts')
    assert parse_archive(json.dumps(legacy))['version'] == 19


def test_imported_entry_proposal_is_off_literal_and_bound_to_origin(client):
    preview = stage(client, json.dumps(card('v3')).encode())
    versions = publish_import(client, preview).json()['versions']
    book = next(item for item in versions if item['kind'] == 'lorebook')
    candidates = client.get(f"/api/versions/{book['id']}/imported-entries").json()
    assert len(candidates) == 3
    candidate = candidates[1]
    url = f"/api/versions/{book['id']}/imported-entry"
    response = client.get(url, params={'import_id': candidate['import_id'], 'path': candidate['path']})
    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal['entry']['enabled'] is False and proposal['entry']['keywords'] == []
    assert proposal['original_fields']['use_regex'] is True
    assert '@@dont_activate' in proposal['entry']['text']
    unrelated = make_book(client)
    assert client.get(f"/api/versions/{unrelated['id']}/imported-entry", params={'import_id': candidate['import_id'], 'path': candidate['path']}).status_code == 404
    content = {**book['content'], 'lore_definition': {'entries': [proposal['entry']]}}
    saved = publish(client, book, content).json()
    assert files(client, saved)[0]['entry_id'] == proposal['entry']['id']
    assert client.get('/api/stories').json() == []


@pytest.mark.parametrize('changes', [
    {'kind': 'required', 'chance_enabled': True}, {'kind': 'required', 'cooldown_beats': 1},
    {'activation': 'keywords', 'keywords': []}, {'secondary_mode': 'exclude', 'secondary': []},
    {'title': '   '}, {'keywords': ['']},
])
def test_invalid_entry_rules_do_not_publish(client, changes):
    value = {**entry(), **changes}
    response = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Invalid', 'content': {'lore_definition': {'entries': [value]}}})
    assert response.status_code == 400
    assert client.get('/api/library').json() == []


def scan_book(entries, **settings):
    return {'asset_id': 'book', 'version_id': 'v1', 'name': 'Book', 'random_stream': 'fixed',
            'definition': LoreDefinition(entries=entries, **settings).model_dump()}


def test_literal_matching_secondary_exclusions_and_required_budget():
    keyword = {**entry(), 'activation': 'keywords', 'keywords': ['quay'], 'secondary_mode': 'exclude', 'secondary': ['closed']}
    literal = {**entry('literal'), 'activation': 'keywords', 'keywords': ['.*']}
    book = scan_book([keyword, literal, entry('off', enabled=False), entry('flavor', kind='flavor')], flavor_budget_tokens=0)
    history = [{'role': 'narrator', 'text': 'The quay is open.'}, {'role': 'ooc', 'text': 'closed .*'}]
    result = select_lore([book], history, advance=True)
    assert [item['title'] for item in result['sources']] == ['Book · Harbor']
    assert result['budgets'][0]['required_tokens'] > 0 and result['draws'] == []
    blocked = select_lore([book], [{'role': 'narrator', 'text': 'The quay is closed.'}], advance=True)
    assert not blocked['sources']
    literal_result = select_lore([book], [{'role': 'narrator', 'text': 'Written .* here'}], advance=True)
    assert [item['title'] for item in literal_result['sources']] == ['Book · Literal']


def test_sticky_cooldown_saved_decisions_and_rng_toggle():
    value = {**entry('flavor', kind='flavor', chance_enabled=True, chance=100, sticky_beats=1, cooldown_beats=2), 'activation': 'keywords', 'keywords': ['quay']}
    book = scan_book([value], scan_messages=1)
    history = [{'role': 'narrator', 'text': 'quay'}]
    first = select_lore([book], history, rng=True, advance=True, seed='fixed')
    frozen = deepcopy(first['after'])
    replay = select_lore([book], history, first['after'], rng=True)
    assert replay['sources'] == first['sources'] and replay['draws'] == [] and first['after'] == frozen
    second = select_lore([book], [{'role': 'narrator', 'text': 'elsewhere'}], first['after'], rng=True, advance=True)
    assert second['sources'] and second['draws'] == []
    third = select_lore([book], history, second['after'], rng=True, advance=True)
    assert not third['sources'] and 'resting' in third['entries'][0]['reason']
    book['definition']['entries'][0]['chance'] = 0
    assert select_lore([book], history, rng=False, advance=True)['sources']
    assert not select_lore([book], history, rng=True, advance=True)['sources']


def test_isolated_preview_reproducible_without_story_or_live_state_changes(client):
    book = make_book(client)
    story = with_book(client, book, 'Untouched Story')
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    body = {'definition': {'entries': [entry('chance', kind='flavor', chance_enabled=True, chance=50)]},
            'passage': 'The next beat.', 'completed_beats': 2, 'prior_passages': ['First beat.', 'Second beat.'], 'master_rng': True, 'seed': 'repeatable'}
    first = client.post('/api/lore/preview', json=body)
    assert first.status_code == 200, first.text
    assert first.json() == client.post('/api/lore/preview', json=body).json()
    assert first.json()['isolated'] and first.json()['after']['clock'] == 3 and len(first.json()['draws']) == 1
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT count(*) FROM mechanic_opportunities').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM generations').fetchone()[0] == 0
    assert client.post('/api/lore/preview', json={**body, 'completed_beats': 1}).status_code == 422
