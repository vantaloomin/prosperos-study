"""Author curation keeps source identity, publication, and recovery separate."""
from copy import deepcopy

import pytest

from server.errors import DomainError
from server.memory.canon_compiler import compile_overview, source_digest
from server.memory.enrichment import enrichment_inputs
from tests.test_archives import backup, restore
from tests.test_library import adoption_request, with_book


def content_with_aids(count=14):
    text, cues = '', []
    for index in range(count):
        passage = f'# Record {index + 1}\n雨 🔑 Elin may return through the northern gate.\n\n'
        start = len(text)
        text += passage
        cues.append({'start': start, 'end': len(text), 'sha256': source_digest(passage),
                     'summary': f'Uncertain return {index + 1}', 'topics': ['testimony'],
                     'aliases': [f'lunar doorway {index + 1}']})
    return {'text': text, 'custom_metadata': {'preserve': True},
            'canon_recall': {'mode': 'relevant', 'cues': cues}}


def preview(client, content, **values):
    response = client.post('/api/canon/cues-preview', json={'content': content, **values})
    assert response.status_code == 200, response.text
    return response.json()


def change_body(content, report, action='edit', **values):
    row = report['items'][0]
    fields = {key: row['cue'][key] for key in ('summary', 'topics', 'aliases')}
    return {'content': content, 'expected_fingerprint': report['fingerprint'],
            'cue_id': row['id'], 'action': action,
            **({'fields': fields} if action == 'edit' else {}), **values}


def database_dump(client):
    with client.app.state.database.connect() as connection:
        return '\n'.join(connection.iterdump())


def test_preview_edit_remove_are_draft_patches_without_database_writes(client):
    content = content_with_aids()
    original = deepcopy(content)
    before = database_dump(client)
    report = preview(client, content)
    assert (report['total'], report['active'], report['stale'], report['next_offset']) == (14, 14, 0, 12)
    body = change_body(content, report)
    body['fields']['summary'] = 'The return is possible, not established.'
    body['fields']['aliases'] = ['unconfirmed homecoming']
    response = client.post('/api/canon/cues-change', json=body)
    assert response.status_code == 200, response.text
    patch = response.json()
    assert set(patch) == {'canon_recall'}
    updated = {**content, **patch}
    assert updated['text'] == original['text'] and updated['custom_metadata'] == original['custom_metadata']
    assert updated['canon_recall']['mode'] == 'relevant'
    old, new = original['canon_recall']['cues'][0], updated['canon_recall']['cues'][0]
    assert all(new[key] == old[key] for key in ('start', 'end', 'sha256'))
    assert new['summary'] == body['fields']['summary'] and new['aliases'] == ['unconfirmed homecoming']
    assert updated['canon_recall']['cues'][1:] == original['canon_recall']['cues'][1:]
    removed = client.post('/api/canon/cues-change', json=change_body(updated, preview(client, updated), 'remove'))
    assert removed.status_code == 200
    assert removed.json()['canon_recall']['cues'] == original['canon_recall']['cues'][1:]
    assert content == original and database_dump(client) == before


def test_filter_and_last_page_clamp_after_removal(client):
    content = content_with_aids(13)
    report = preview(client, content, offset=12)
    assert [row['number'] for row in report['items']] == [13] and report['next_offset'] is None
    response = client.post('/api/canon/cues-change', json=change_body(content, report, 'remove'))
    content.update(response.json())
    report = preview(client, content, offset=12)
    assert report['offset'] == 0 and len(report['items']) == 12
    filtered = preview(client, content, query='LUNAR DOORWAY 12')
    assert filtered['matches'] == 1 and filtered['items'][0]['number'] == 12
    empty = preview(client, content, query='unknown phrase', offset=1000)
    assert empty['items'] == [] and empty['offset'] == 0 and empty['next_offset'] is None


def test_stale_source_uses_preserved_publication_never_changed_prose(client):
    content = content_with_aids(1)
    book = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Gate', 'content': content}).json()
    original = content['text']
    content['text'] = content['text'].replace('Elin may return', 'Elin did leave')
    report = preview(client, content, source_version_id=book['id'], status='stale')
    assert (report['active'], report['stale'], report['matches']) == (0, 1, 1)
    row = report['items'][0]
    assert row['source']['text'] == original and row['source']['origin'] == 'published' and row['source']['version'] == 1
    response = client.post('/api/canon/cues-change', json=change_body(content, report, fields={'summary': 'Revised cue only.', 'topics': [], 'aliases': []}))
    content.update(response.json())
    assert preview(client, content)['items'][0]['source'] is None
    assert preview(client, content, status='active')['items'] == []
    compiled = client.post('/api/canon/compile-preview', json={'content': content}).json()
    assert compiled['active_cues'] == 0 and compiled['stale_cues'] == 1
    assert all(not row['search_cues']['summary'] for row in compiled['items'])
    content['text'] = original
    assert preview(client, content)['active'] == 1


def test_unicode_source_paging_and_import_limits_are_lossless(client):
    content = content_with_aids(1)
    prefix = 'Outside the source.\n'
    source = '雨🔑' * 2600
    cue = content['canon_recall']['cues'][0]
    cue.update(start=len(prefix), end=len(prefix + source), sha256=source_digest(source),
               summary='s' * 32000, topics=['t' * 2000] * 256, aliases=['  line one\nline two  ', 'a' * 2000])
    content['text'] = prefix + source + '\nOutside again.'
    first = preview(client, content)
    row = first['items'][0]
    pieces = [row['source']['text']]
    offset = row['source']['next_offset']
    while offset is not None:
        page = preview(client, content, cue_id=row['id'], source_offset=offset)['items'][0]['source']
        pieces.append(page['text'])
        offset = page['next_offset']
    assert ''.join(pieces) == source
    assert preview(client, content, cue_id=row['id'], source_offset=999999)['items'][0]['source']['offset'] == 4800
    response = client.post('/api/canon/cues-change', json=change_body(content, first))
    assert response.status_code == 200, response.text
    assert response.json()['canon_recall'] == content['canon_recall']


@pytest.mark.parametrize('change', ['draft', 'aid'])
def test_changed_draft_or_aid_rejects_old_selection(client, change):
    content = content_with_aids(1)
    report = preview(client, content)
    body = change_body(content, report)
    if change == 'draft':
        body['content']['text'] += 'Another edit.'
    else:
        body['cue_id'] = '0' * 64
    assert client.post('/api/canon/cues-change', json=body).status_code == 409
    assert client.post('/api/canon/cues-preview', json={'content': content, 'cue_id': '0' * 64}).status_code == 409


@pytest.mark.parametrize(('field', 'value', 'status'), [
    ('start', 7, 422), ('sha256', '0' * 64, 422), ('publish', True, 422),
    ('summary', 's' * 32001, 422), ('topics', ['x'] * 257, 422),
    ('aliases', ['x' * 2001], 400),
])
def test_edit_limits_and_source_identity_cannot_be_bypassed(client, field, value, status):
    content = content_with_aids(1)
    body = change_body(content, preview(client, content))
    body['fields'][field] = value
    assert client.post('/api/canon/cues-change', json=body).status_code == status


def test_action_payloads_cannot_silently_discard_edits(client):
    content = content_with_aids(1)
    body = change_body(content, preview(client, content), 'remove', fields={'summary': 'Do not lose me', 'topics': [], 'aliases': []})
    assert client.post('/api/canon/cues-change', json=body).status_code == 400
    body.update(action='edit', fields=None)
    assert client.post('/api/canon/cues-change', json=body).status_code == 400


def test_removing_stale_aid_unblocks_fresh_enrichment_without_reattaching(client):
    content = content_with_aids(1)
    content['text'] = content['text'].replace('northern', 'southern')
    chunks, _ = compile_overview('draft', 'Gate', content)
    with pytest.raises(DomainError, match='existing cue'):
        enrichment_inputs('Gate', content, [chunks[0].id])
    response = client.post('/api/canon/cues-change', json=change_body(content, preview(client, content), 'remove'))
    content.update(response.json())
    assert preview(client, content)['total'] == 0
    assert 'southern' in enrichment_inputs('Gate', content, [chunks[0].id])['text']


def test_publication_adoption_and_archive_preserve_old_aids(client):
    content = content_with_aids(1)
    book = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Gate', 'content': content}).json()
    story = with_book(client, book, 'Original edition')
    body = change_body(content, preview(client, content))
    body['fields']['aliases'] = ['New reviewed phrase']
    edited = {**content, **client.post('/api/canon/cues-change', json=body).json()}
    version = client.post(f"/api/library/{book['asset_id']}/versions", json={
        'expected_version_id': book['id'], 'name': book['name'], 'content': edited}).json()
    assert version['number'] == 2
    endpoint = '/api/stories/' + story['story_id']
    assert client.get(endpoint).json()['attachments'][0]['version_id'] == book['id']
    adoption = f"/api/versions/{version['id']}/adoption"
    assert client.post(adoption, json=adoption_request(client.get(adoption).json())).json() == {'updated': 1}
    assert client.get(endpoint).json()['attachments'][0]['version_id'] == version['id']
    file, _ = backup(client)
    _, mapping = restore(client, file)
    versions = client.get(f"/api/library/{mapping[book['asset_id']]}/versions").json()
    restored = {row['number']: row['content'] for row in versions}
    assert restored[1]['canon_recall'] == content['canon_recall']
    assert restored[2]['canon_recall'] == edited['canon_recall']
    assert restored[1]['text'] == restored[2]['text'] == content['text']
