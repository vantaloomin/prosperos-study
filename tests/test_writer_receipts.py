"""Receipts must match originals even when an altered request is rehashed."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from server.archives.format import canonical
from server.archives.validate import parse_archive
from server.archives.writer_sources import digest
from server.database import decode, encode
from server.errors import DomainError
from server.main import create_app
from server.memory.budget import token_estimate
from tests.test_archives import backup, restore
from tests.test_canon_memory import imported_book
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_memory import fixture_context, small_profile


def saved_story(client):
    small_profile(client)
    book, _, _ = imported_book(client)
    story = client.post('/api/stories', json={'title': 'Exact source audit', 'settings': {'memory': {'mode': 'long'}},
        'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
    for index, node in enumerate(fixture_context()['history']):
        append(client, story['branch_id'], node['text'], index)
    client.app.state.runner.provider = DraftProvider()
    result = client.post('/api/branches/' + story['branch_id'] + '/generations', json={
        'operation_id': uuid4().hex, 'expected_revision': 42,
        'direction': 'Remember the promise about the observatory key. Moon orchids and iron dust.'})
    assert result.status_code == 201, result.text
    generation = finished(client, result.json()['id'])
    packet = decode(generation['snapshot']['content'])
    assert packet['recalled_passages'] and packet['recalled_canon']
    return story, generation


@pytest.fixture(scope='module')
def saved_archive(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp('writer-receipts') / 'test.sqlite3'),
                    headers={'x-roleplay-client': 'workspace'}) as client:
        story, _ = saved_story(client)
        return backup(client, story)[1]


def altered(document):
    copy = deepcopy(document)
    row = copy['data']['generations'][0]
    snapshot = decode(row['snapshot'])
    return copy, row, snapshot, decode(snapshot['content'])


def rehash(row, snapshot, content):
    snapshot['content'] = encode(content)
    snapshot['memory']['content_sha256'] = digest(snapshot['content'])
    snapshot['estimated_input_tokens'] = token_estimate(snapshot['prompt']['template'], content)
    row['snapshot'] = encode(snapshot)


@pytest.mark.parametrize('change', ['whole-text', 'whole-role', 'whole-source', 'whole-manifest', 'whole-order', 'drop-head',
    'excerpt-text', 'excerpt-offset', 'excerpt-source', 'excerpt-position', 'excerpt-title', 'excerpt-kind',
    'selection-source', 'selection-missing', 'selection-score', 'selection-reason', 'duplicate-excerpt',
    'coverage', 'fingerprint', 'content-hash', 'removed-receipt', 'algorithm', 'current-neighbor'])
def test_writer_rejects_rehashed_prose_and_receipt_corruption(saved_archive, change):
    archive, row, snapshot, content = altered(saved_archive)
    item = content['recalled_passages'][0]
    memory = snapshot['memory']
    actions = {
        'whole-text': lambda: content['history'][-1].update(text='Invented future event.'),
        'whole-role': lambda: content['history'][-1].update(role='ooc'),
        'whole-source': lambda: content['history'][-1].update(id=content['history'][0]['id']),
        'whole-manifest': lambda: content['history'][-1].update(manifest_id='foreign'),
        'whole-order': lambda: content['history'].reverse(),
        'drop-head': lambda: content['history'].pop(),
        'excerpt-text': lambda: item.update(text='Mara already returned the key.'),
        'excerpt-offset': lambda: item.update(start=1),
        'excerpt-source': lambda: item.update(source_id='message:foreign'),
        'excerpt-position': lambda: item.update(passage_number=2),
        'excerpt-title': lambda: item.update(title='Established truth'),
        'excerpt-kind': lambda: item.update(kind='Canon fact'),
        'selection-source': lambda: memory['selected'][0].update(source_id='message:foreign'),
        'selection-missing': lambda: memory['selected'].clear(),
        'selection-score': lambda: memory['selected'][0].update(score=float('nan')),
        'selection-reason': lambda: memory['selected'][0].update(reason='Another reason'),
        'duplicate-excerpt': lambda: content['recalled_passages'].append(deepcopy(item)),
        'coverage': lambda: memory['coverage'].update(complete_path=True),
        'fingerprint': lambda: memory.update(source_fingerprint='0' * 64),
        'algorithm': lambda: memory.update(algorithm='prospero-lexical-v99'),
        'current-neighbor': lambda: item.update(adjacent_to=item['id']),
    }
    if change not in {'content-hash', 'removed-receipt'}:
        actions[change]()
    rehash(row, snapshot, content)
    if change == 'content-hash':
        snapshot['memory']['content_sha256'] = '0' * 64
        row['snapshot'] = encode(snapshot)
    if change == 'removed-receipt':
        del snapshot['memory']
        row['snapshot'] = encode(snapshot)
    with pytest.raises(DomainError):
        parse_archive(canonical(archive))


@pytest.mark.parametrize('change', ['text', 'identity', 'offset', 'authority', 'collection', 'missing', 'metadata', 'compiler', 'duplicate'])
def test_writer_rejects_rehashed_canon_corruption(saved_archive, change):
    archive, row, snapshot, content = altered(saved_archive)
    item = content['recalled_canon'][0]
    receipt = snapshot['memory']['canon']
    actions = {
        'text': lambda: item.update(text='A fabricated world rule.'),
        'identity': lambda: content['library'][0].update(version_id='wrong'),
        'offset': lambda: item.update(end=item['end'] - 1),
        'authority': lambda: item.update(knowledge='The character knows this.'),
        'collection': lambda: receipt['collections'][0].update(selected_chunks=77),
        'missing': lambda: snapshot['memory'].pop('canon'),
        'metadata': lambda: content['library'][0]['version'].update(name='A different edition'),
        'compiler': lambda: receipt['collections'][0].update(source_sha256='0' * 64),
        'duplicate': lambda: content['recalled_canon'].append(deepcopy(item)),
    }
    actions[change]()
    rehash(row, snapshot, content)
    with pytest.raises(DomainError):
        parse_archive(canonical(archive))


def test_receipt_validation_does_not_rerank_and_reports_verified_sources(saved_archive, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Archive validation must not rerank or generate.')
    monkeypatch.setattr('server.memory.retrieval.Corpus.search', forbidden)
    report = {}
    parsed = parse_archive(canonical(saved_archive), verification=report)
    assert report == {'checked': 1, 'complete': 1, 'limited': 0, 'limitations': []}
    assert parsed['data']['generations'] == saved_archive['data']['generations']


def test_old_algorithm_is_preserved_with_an_explicit_limit(saved_archive):
    archive, row, snapshot, content = altered(saved_archive)
    snapshot['memory']['algorithm'] = 'prospero-lexical-v4'
    rehash(row, snapshot, content)
    report = {}
    parsed = parse_archive(canonical(archive), verification=report)
    assert report['limited'] == 1 and report['complete'] == 0 and 'older receipt algorithm' in report['limitations'][0]
    assert parsed['data']['generations'] == archive['data']['generations']


def legacy_portable(client):
    story, generation = saved_story(client)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied_story = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    _, document = backup(client, copied_story)
    document['version'] = 27
    for table in ('continuity_edits', 'branch_continuity_edits'):
        assert document['data'].pop(table) == []
    del document['data']['archive_identities']  # Exact shape written by the pre-identity app after a restore.
    return document, generation


def test_old_portable_archive_stays_restorable_and_never_claims_verified_identity(client, tmp_path):
    document, generation = legacy_portable(client)
    with TestClient(create_app(tmp_path / 'fresh-install.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        fresh.app.state.runner.provider = DraftProvider()
        response = fresh.post('/api/archives/imports', json={'content': canonical(document)})
        assert response.status_code == 201, response.text
        file = response.json()
        report = file['summary']['writer_verification']
        assert report['limited'] == 1 and report['complete'] == 0 and 'original source IDs' in report['limitations'][0]
        _, mapping = restore(fresh, file)
        current = {'story_id': mapping[document['selection']['storyId']], 'branch_id': mapping[document['selection']['branchId']]}
        again, saved = backup(fresh, current)
        assert again['summary']['writer_verification']['limited'] == 1
        assert decode(saved['data']['generations'][0]['snapshot'])['content'] == generation['snapshot']['content']
        assert len(fresh.app.state.runner.provider.calls) == 0
    assert len(client.app.state.runner.provider.calls) == 1


def test_local_exact_restore_maps_can_recover_a_portable_archives_missing_ids(client):
    document, _ = legacy_portable(client)
    file = client.post('/api/archives/imports', json={'content': canonical(document)}).json()
    assert file['summary']['writer_verification']['limited'] == 1
    _, mapping = restore(client, file)
    current = {'story_id': mapping[document['selection']['storyId']], 'branch_id': mapping[document['selection']['branchId']]}
    recovered, _ = backup(client, current)
    assert recovered['summary']['writer_verification']['complete'] == 1


def test_legacy_limit_does_not_allow_fabricated_prose(client):
    document, _ = legacy_portable(client)
    archive, row, snapshot, content = altered(document)
    content['recalled_passages'][0]['text'] = 'An event that never happened.'
    rehash(row, snapshot, content)
    before = client.get('/api/stories').json()
    response = client.post('/api/archives/imports', json={'content': canonical(archive)})
    assert response.status_code == 400 and client.get('/api/stories').json() == before


def test_repeated_import_and_retry_keep_provider_bytes_and_verified_sources(client):
    story, generation = saved_story(client)
    expected = generation['snapshot']['content']
    for _ in range(2):
        file, document = backup(client, story)
        assert file['summary']['writer_verification']['complete'] == 1
        _, mapping = restore(client, file)
        story = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
        assert decode(document['data']['generations'][0]['snapshot'])['content'] == expected
    candidate_id = mapping[document['data']['candidates'][0]['id']]
    # Retry uses the recorded input even after the live story grows.
    append(client, story['branch_id'], 'A new event after the saved request.', 42)
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE candidates SET status='error' WHERE id=?", (candidate_id,))
    response = client.post('/api/candidates/' + candidate_id + '/retry')
    assert response.status_code == 200, response.text
    result = finished(client, mapping[document['data']['generations'][0]['id']])
    assert result['snapshot']['content'] == expected
    assert backup(client, story)[0]['summary']['writer_verification']['complete'] == 1


@pytest.mark.parametrize('value', [[], False, 'receipt', 123])
def test_malformed_receipt_types_fail_as_domain_errors(saved_archive, value):
    archive, row, snapshot, _ = altered(saved_archive)
    snapshot['memory'] = value
    row['snapshot'] = encode(snapshot)
    with pytest.raises(DomainError):
        parse_archive(canonical(archive))


def test_saved_older_archive_can_be_reviewed_without_restoring_or_mutating_it(client):
    from server.archives.service import Archives
    story, _ = saved_story(client)
    file, _ = backup(client, story)
    with client.app.state.database.connect(write=True) as connection:
        value = decode(connection.execute('SELECT summary FROM archive_files WHERE id=?', (file['id'],)).fetchone()['summary'])
        value.pop('writer_verification')
        connection.execute('UPDATE archive_files SET summary=? WHERE id=?', (encode(value), file['id']))
    before = client.get('/api/stories').json()
    response = client.get('/api/archives/' + file['id'] + '/review')
    assert response.status_code == 200 and response.json()['summary']['writer_verification']['complete'] == 1
    assert client.get('/api/stories').json() == before
    assert all('writer_verification' not in item['summary'] for item in client.get('/api/archives').json())
    _, path = Archives(client.app.state.database).file(file['id'])
    path.write_text(path.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    changed = client.get('/api/archives/' + file['id'] + '/review')
    assert changed.status_code == 409 and client.get('/api/stories').json() == before
