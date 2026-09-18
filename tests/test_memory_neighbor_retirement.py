"""New requests use ranked evidence; saved neighboring-source requests still replay."""
import json
from pathlib import Path

import pytest

from server.errors import DomainError
from server.memory.packet import assemble_memory
from server.memory.source_packet import assemble_sources
from server.memory.source_replay import replay_sources
from tests.test_memory import profiles
from tests.test_memory_neighbors import neighbor_rows, pair_context, specialist_context
from tests.test_source_memory import saved

CAPTURE = Path(__file__).parent / 'fixtures/retired_neighbor_receipts.json'


@pytest.mark.parametrize('budget', [4096, 8192])
def test_new_writer_and_specialist_requests_do_not_automatically_expand_neighbors(budget):
    writer, writer_receipt = assemble_memory(pair_context(), 'Write.', profiles(budget))
    specialist, source_receipt = assemble_sources(specialist_context(), 'Review.', profiles(budget), {'mode': 'long'})
    assert not neighbor_rows(writer_receipt) and not neighbor_rows(source_receipt)
    assert writer_receipt['algorithm'] == 'prospero-lexical-v6'
    assert source_receipt['algorithm'] == 'prospero-source-lexical-v5'
    assert all('adjacent_to' not in item for item in writer.get('recalled_passages', []))
    assert all('recall_relation' not in item for item in specialist['sources'])
    assert replay_sources(specialist_context(), saved(specialist_context(), specialist, source_receipt)) == specialist


def test_literal_pre_withdrawal_specialist_receipt_replays_without_retrieval(monkeypatch):
    captured = json.loads(CAPTURE.read_text(encoding='utf-8'))['specialist']
    assert captured['receipt']['algorithm'] == 'prospero-source-lexical-v3'
    assert len(neighbor_rows(captured['receipt'])) == 1
    def forbidden(*_args, **_kwargs):
        pytest.fail('Frozen replay must not consult current retrieval')
    monkeypatch.setattr('server.memory.source_packet.candidates', forbidden)
    context, packet, receipt = (captured[key] for key in ('context', 'packet', 'receipt'))
    assert replay_sources(context, saved(context, packet, receipt)) == packet


def test_new_receipt_cannot_smuggle_in_retired_proximity_selection():
    captured = json.loads(CAPTURE.read_text(encoding='utf-8'))['specialist']
    context, packet, receipt = (captured[key] for key in ('context', 'packet', 'receipt'))
    receipt['algorithm'] = 'prospero-source-lexical-v5'
    with pytest.raises(DomainError, match='Unsupported neighboring evidence'):
        replay_sources(context, saved(context, packet, receipt))
