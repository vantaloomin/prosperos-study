import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.prompt_sections import system_prompt
from tests.archive_legacy import remove_v062_prompts, remove_v07_records
from tests.test_archives import backup, restore

FIXTURE = Path(__file__).parent / 'fixtures' / 'v070-manuscript-archive.json.gz'


def test_actual_released_v070_manuscript_and_writer_bytes_survive_restore(client):
    raw = gzip.decompress(FIXTURE.read_bytes()).decode('utf-8')
    original = json.loads(raw)
    assert original['version'] == 33 and len(original['data']['manuscripts']) == 1
    assert parse_archive(raw)['version'] == ARCHIVE_VERSION
    stage = client.post('/api/archives/imports', json={'content': raw})
    assert stage.status_code == 201, stage.text
    _, mapping = restore(client, stage.json())
    manuscript = original['data']['manuscripts'][0]
    result = client.get('/api/stories/' + mapping[manuscript['story_id']] + '/manuscript').json()
    source = decode(manuscript['document'])
    assert result['document']['title'] == source['title'] == 'The Lens Ledger'
    scene = result['document']['chapters'][0]['scenes'][0]
    for key in ('branch_id', 'head_id', 'from_node_id', 'through_node_id'):
        assert scene[key] == mapping[source['chapters'][0]['scenes'][0][key]]
    assert result['document']['bookmarks'][0]['node_id'] == mapping[source['bookmarks'][0]['node_id']]
    run = original['data']['generations'][0]
    restored = client.get('/api/generations/' + mapping[run['id']]).json()
    snapshot = decode(run['snapshot'])
    assert restored['snapshot']['content'] == snapshot['content']
    assert system_prompt(restored['snapshot']) == system_prompt(snapshot)
    backup(client, {'story_id': mapping[manuscript['story_id']], 'branch_id': scene['branch_id']})


@pytest.mark.parametrize('version', [31, 32, 33, 34, 35, 36])
def test_memory_development_archives_keep_their_record_shape(client, story, version):
    _, document = backup(client, story)
    remove_v062_prompts(document, keep_memory=True)
    document['version'] = version
    if version < 34:
        for key in ('relationship_jobs', 'relationship_attempts'):
            document['data'].pop(key)
    if version < 33:
        document['data'].pop('branch_cleanup_timing')
    if version < 32:
        for key in ('branch_cleanup_settings', 'candidate_cleanups'):
            document['data'].pop(key)
    upgraded = parse_archive(encode(document))
    assert upgraded['version'] == ARCHIVE_VERSION
    assert upgraded['data']['stories'] == document['data']['stories']
    assert upgraded['data']['manuscripts'] == []


def test_released_v32_prompt_shape_and_ambiguous_partial_shapes(client, story):
    _, document = backup(client, story)
    remove_v07_records(document)
    document['version'] = 32
    assert parse_archive(encode(document))['version'] == ARCHIVE_VERSION
    broken = deepcopy(document)
    broken['data']['candidate_cleanups'] = []
    with pytest.raises(DomainError, match='original record groups'):
        parse_archive(encode(broken))
    broken = deepcopy(document)
    broken['prompt_heads'].pop('review-blind')
    with pytest.raises(DomainError, match='original record groups'):
        parse_archive(encode(broken))
