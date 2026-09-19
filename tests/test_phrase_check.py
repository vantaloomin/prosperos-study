from uuid import uuid4

import pytest

from server.phrases import service
from server.phrases.detection import detect, tokens
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_passage_revisions import revise
from tests.test_profiles import make_profile

PHRASE = 'silver birds gather quietly'


def add(client, branch, text, role='narrator'):
    revision = client.get('/api/branches/' + branch).json()['revision']
    response = client.post(f'/api/branches/{branch}/messages', json={
        'operation_id': uuid4().hex, 'expected_revision': revision, 'text': text, 'role': role})
    assert response.status_code == 201, response.text
    return response.json()['node_id']


def scan(client, branch, **extra):
    revision = client.get('/api/branches/' + branch).json()['revision']
    response = client.post(f'/api/branches/{branch}/phrase-check', json={'expected_revision': revision, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def node(text, index=0):
    return {'id': str(index), 'text': text, 'role': 'narrator'}


def test_exact_evidence_retains_unicode_apostrophes_function_words_and_original_offsets():
    passages = [node(text, i) for i, text in enumerate([
        '🌙 She let out a breath. The café’s shutters opened.',
        "She  let out a breath! The CAFE\u0301'S shutters rattled.",
        'Again, she let out a breath; the café’s shutters closed.',
    ])]
    findings, _ = detect(passages)
    assert any(item['phrase'] == 'she let out a breath' for item in findings)
    assert any(item['phrase'] == "the café's shutters" for item in findings)
    for finding in findings:
        assert finding['count'] == 3
        for evidence in finding['evidence']:
            original = passages[int(evidence['node_id'])]['text']
            assert original[evidence['start']:evidence['end']] == evidence['quote']
    assert tokens('same-id', 'Changed source words') != tokens('same-id', 'Unchanged original words')


def test_sentence_and_paragraph_boundaries_common_words_and_self_overlap():
    assert detect([node('Silver birds. Gather quietly. ' * 4)])[0] == []
    assert detect([node('Silver birds\ngather quietly\n' * 4)])[0] == []
    assert detect([node('It was as if. It was as if. It was as if.')])[0] == []
    assert detect([node('echo echo echo echo echo')], minimum=2)[0] == []
    findings, _ = detect([node('Silver birds gather quietly. ' * 3)])
    assert len(findings) == 1 and findings[0]['count'] == 3 and findings[0]['passage_count'] == 1


def test_changed_occurrences_get_new_ids_but_phrase_identity_is_stable():
    originals = [node(PHRASE + '.', i) for i in range(3)]
    first = detect(originals)[0][0]
    second = detect([*originals, node(PHRASE + '.', 3)])[0][0]
    assert first['id'] != second['id']
    assert first['phrase_id'] == second['phrase_id']
    assert detect(originals)[0][0] == first


def test_evidence_count_is_complete_when_display_is_capped():
    findings, _ = detect([node(PHRASE + '.', i) for i in range(12)])
    assert findings[0]['count'] == 12
    assert len(findings[0]['evidence']) == 8 and findings[0]['omitted_evidence'] == 4
    assert [source['node_id'] for source in findings[0]['evidence']] == ['0', '1', '6', '7', '8', '9', '10', '11']


def test_distinct_groups_are_capped_with_explicit_overflow():
    text = ' '.join(f'copper{index} lantern{index} window{index}. ' * 3 for index in range(35))
    findings, more = detect([node(text)])
    assert len(findings) == 30 and more
    assert all(item['count'] == 3 for item in findings)


def test_dense_repetition_preserves_full_counts_without_nested_fragment_noise():
    findings, more = detect([node((PHRASE + '. ') * 3000)])
    assert len(findings) == 1 and not more
    assert findings[0]['count'] == 3000 and findings[0]['omitted_evidence'] == 2992


def test_scan_is_read_only_and_excludes_notes_unaccepted_drafts_library_and_other_paths(client, story):
    branch = story['branch_id']
    original = add(client, branch, PHRASE + '.')
    add(client, branch, PHRASE + '.', role='user')
    add(client, branch, PHRASE + '.', role='assistant')
    add(client, branch, 'HIDDEN AUTHOR NOTE. ' * 10, role='ooc')
    client.post('/api/library', json={'kind': 'lorebook', 'name': 'Private book', 'content': {'text': 'HIDDEN LIBRARY TEXT. ' * 10}})
    fork = client.post(f'/api/branches/{branch}/forks', json={'operation_id': uuid4().hex,
        'expected_revision': 4, 'node_id': original, 'name': 'Sibling'}).json()['branch_id']
    add(client, fork, 'HIDDEN SIBLING PROSE. ' * 10)
    other = client.post('/api/stories', json={'title': 'Other', 'opening_text': 'HIDDEN OTHER STORY. ' * 10}).json()
    make_profile(client, 'Fixture writer', primary=True)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    finished(client, generate(client, story, revision=4)['id'])
    before_calls = len(provider.calls)
    with client.app.state.database.connect() as connection:
        before = list(connection.iterdump())
    report = scan(client, branch, scope='path')
    assert report['passage_count'] == 3 and report['findings'][0]['count'] == 3
    assert 'HIDDEN' not in str(report) and len(provider.calls) == before_calls
    assert scan(client, branch, scope='path') == report
    assert scan(client, other['branch_id'])['findings']
    with client.app.state.database.connect() as connection:
        assert list(connection.iterdump()) == before


def test_removal_undo_and_past_edit_use_their_own_accepted_prose(client, story):
    branch = story['branch_id']
    ids = [add(client, branch, PHRASE + '.') for _ in range(3)]
    report = scan(client, branch)
    removed = revise(client, branch, ids[1])
    assert scan(client, removed['branch_id'])['findings'] == []
    assert scan(client, branch) == report
    restored = revise(client, removed['branch_id'], removed['node_id'], 'restore')
    assert scan(client, restored['branch_id'])['findings'][0]['count'] == 3
    edited = client.post(f'/api/branches/{branch}/forks', json={'operation_id': uuid4().hex,
        'expected_revision': 3, 'node_id': ids[1], 'name': 'Changed past', 'replacement': 'A different scene.'}).json()
    assert scan(client, edited['branch_id'])['findings'] == []


def test_recent_scope_counts_prose_only_and_limits_never_split_a_passage(client, story, monkeypatch):
    branch = story['branch_id']
    for i in range(22):
        add(client, branch, f'{PHRASE}. Unique token{i}.')
    add(client, branch, 'A direction.', role='ooc')
    assert scan(client, branch)['passage_count'] == 20
    assert scan(client, branch, scope='path')['passage_count'] == 22
    monkeypatch.setattr(service, 'MAX_CHARACTERS', 100)
    report = scan(client, branch, scope='path', minimum=2)
    assert report['limited'] and report['passage_count'] == 2
    assert report['characters'] <= 100 and report['findings'][0]['count'] == 2
    monkeypatch.setattr(service, 'MAX_TOKENS', 1)
    report = scan(client, branch)
    assert report['limited'] and report['passage_count'] == 0 and report['findings'] == []


@pytest.mark.parametrize('extra,status', [({'expected_revision': 8}, 409), ({'minimum': 1}, 422),
                                        ({'scope': 'siblings'}, 422), ({'enabled': True}, 422)])
def test_invalid_or_stale_requests_are_rejected(client, story, extra, status):
    response = client.post(f'/api/branches/{story["branch_id"]}/phrase-check', json={'expected_revision': 0, **extra})
    assert response.status_code == status


def test_empty_path_and_path_change_during_analysis(client, story, monkeypatch):
    branch = story['branch_id']
    assert scan(client, branch)['passage_count'] == 0
    original = service.detect

    def advance(passages, minimum):
        result = original(passages, minimum)
        add(client, branch, 'The path has advanced.')
        return result

    monkeypatch.setattr(service, 'detect', advance)
    response = client.post(f'/api/branches/{branch}/phrase-check', json={'expected_revision': 0})
    assert response.status_code == 409 and 'changed while checking' in response.json()['detail']


def test_archive_roundtrip_rebuilds_evidence_with_restored_source_ids(client, story):
    branch = story['branch_id']
    for _ in range(3):
        add(client, branch, PHRASE + '.')
    report = scan(client, branch)
    archive, _ = backup(client, story)
    _, mapping = restore(client, archive)
    restored = scan(client, mapping[branch])
    assert restored['findings'][0]['phrase_id'] == report['findings'][0]['phrase_id']
    assert restored['findings'][0]['count'] == 3
    assert [source['node_id'] for source in restored['findings'][0]['evidence']] == [
        mapping[source['node_id']] for source in report['findings'][0]['evidence']]
