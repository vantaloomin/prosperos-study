from uuid import uuid4

import pytest

from scripts.manuscript_memory_evaluation import build_context, snapshot_for
from scripts.memory_literature_fixture import literature_fixture
from scripts.memory_literature_metrics import evidence_coverage
from scripts.memory_quality_metrics import exact_ranges
from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.generations import record_generation
from server.memory.group_packet import present_ids
from server.memory.writer_recall_packet import pack_recall
from server.prompts import DEFAULT_WRITER
from tests.test_archives import backup, restore
from tests.test_generations import finished
from tests.test_writer_recall import RecallProvider, setup_story


@pytest.mark.parametrize('probe_id', ['doll-false-signature', 'machine-expertise', 'machine-decay'])
def test_new_packing_keeps_already_supplied_query_evidence_within_original_budget(probe_id):
    stories, probes = literature_fixture()
    probe = next(row for row in probes if row['id'] == probe_id)
    story = stories[probe['story']]
    snapshot = snapshot_for(build_context(story, probe), {'config': {'context_tokens': 8192, 'max_output_tokens': 512}}, DEFAULT_WRITER)
    originals = {row['id']: row['text'] for row in story['sources']}
    expected = len(probe['evidence'])
    for version in (4, 5):
        snapshot['writer_recall']['version'] = version
        result = pack_recall(snapshot, [probe['query']])
        final = result['final_input']
        packet = decode(final['content'])
        measured = evidence_coverage(probe, exact_ranges(packet, originals))
        assert measured['found_groups'] == (expected if version == 5 else 0)
        if version == 5:
            supplied = present_ids(packet, snapshot['writer_recall']['sources'])
            assert all(row['id'] in supplied for row in result['decisions'] if row['fate'] in {'already supplied', 'selected'})
        assert result['evidence_tokens'] <= result['evidence_allowance']
        assert len(result['decisions']) <= 8
        assert final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= final['memory']['input_allowance']


def test_frozen_v4_request_generates_and_survives_v34_archive_migration(client):
    story, nodes = setup_story(client)
    from tests.archive_legacy import remove_v062_prompts
    from tests.test_memory_readiness import settings
    settings(client, story, prompt_sections=False)
    database = client.app.state.database
    with database.connect() as connection:
        snapshot, profiles = generation_snapshot(connection, story['branch_id'], GenerateRequest(
            operation_id=uuid4().hex, expected_revision=len(nodes)))
    snapshot['writer_recall']['version'] = 4
    original_bytes = snapshot['content']
    with database.connect(write=True) as connection:
        run = record_generation(connection, snapshot, profiles)
    client.app.state.runner.provider = RecallProvider()

    async def complete():
        client.app.state.runner.start(run['candidate_ids'][0])
        await client.app.state.runner.tasks[run['candidate_ids'][0]]

    client.portal.call(complete)
    candidate = finished(client, run['id'])['candidates'][0]
    receipt = candidate['usage']['writer_recall']
    assert receipt['version'] == 4
    file, archive = backup(client, story)
    remove_v062_prompts(archive, keep_memory=True)
    migrated = parse_archive(encode({**archive, 'version': 34}))
    assert migrated['version'] == ARCHIVE_VERSION
    saved = decode(migrated['data']['generations'][0]['snapshot'])
    assert saved['content'] == original_bytes and saved['writer_recall']['version'] == 4
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]
    assert restored['usage']['writer_recall'] == receipt
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
