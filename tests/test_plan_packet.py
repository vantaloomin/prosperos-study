from copy import deepcopy

from server.memory.packet import assemble_memory, token_estimate
from tests.test_memory import fixture_context, profiles
from tests.test_planned_events import AGREEMENT, plan


def context_with_plans(count=2):
    context = fixture_context()
    context['direction'] = 'I cannot go this weekend.'
    context['history'][-1]['text'] = 'Mara put down her cup and sighed.'
    context['continuity']['entries'] = [
        {'id': f'plan-{index}', 'kind': 'plan', 'subject': 'Camping trip' if index == 0 else f'Museum visit {index}',
         'text': AGREEMENT, 'plan': plan(), 'status': 'active', 'node_id': 'n0', 'commit_id': 'c1',
         'evidence': [{'source_id': 'scene:checked', 'quote': AGREEMENT}]} for index in range(count)]
    return context


def test_indirect_reference_keeps_competing_plans_and_exact_support():
    context = context_with_plans()
    original = deepcopy(context)
    packet, receipt = assemble_memory(context, 'Write.', profiles(4096))
    assert context == original
    assert {item['subject'] for item in packet['plan_memory']['entries']} == {'Camping trip', 'Museum visit 1'}
    assert packet['continuity']['entries'] == []
    assert receipt['plans']['omitted_ids'] == []
    assert packet['plan_memory']['omitted_count'] == 0
    assert all(item['evidence'][0]['quote'] == AGREEMENT for item in packet['plan_memory']['entries'])
    assert 'preserve that ambiguity' in packet['plan_memory']['rule']
    assert token_estimate('Write.', packet) + receipt['overhead_margin'] <= 4096 - 512


def test_many_plans_are_bounded_and_omissions_are_disclosed():
    context = context_with_plans(60)
    packet, receipt = assemble_memory(context, 'Write.', profiles(2048))
    supplied = packet['plan_memory']['entries']
    assert 0 < len(supplied) < 60
    assert len(supplied) + packet['plan_memory']['omitted_count'] == 60
    assert len(receipt['plans']['omitted_ids']) == packet['plan_memory']['omitted_count']
    assert token_estimate('Write.', packet) + receipt['overhead_margin'] <= 2048 - 512


def test_full_history_preserves_all_plans_and_history():
    context = context_with_plans(10)
    context['story']['settings']['memory']['mode'] = 'full'
    packet, receipt = assemble_memory(context, 'Write.', profiles(1024))
    assert packet is context and receipt is None
    assert len(packet['continuity']['entries']) == 10


def test_attempted_delivery_remains_unfinished_and_completed_plan_keeps_outcome():
    context = context_with_plans(1)
    entry = context['continuity']['entries'][0]
    entry.update(subject='Letter delivery', text='Mara handed the letter to a courier, who lost it.')
    entry['plan']['status'] = 'attempted'
    packet, _ = assemble_memory(context, 'Write.', profiles(4096))
    assert packet['plan_memory']['entries'][0]['plan']['status'] == 'attempted'
    assert packet['plan_memory']['entries'][0]['plan']['resolution'] is None
    entry['plan'].update(status='completed', resolution='Ivo received and read the letter.')
    entry['status'] = 'resolved'
    context['direction'] = 'What happened to the letter delivery?'
    packet, _ = assemble_memory(context, 'Write.', profiles(4096))
    assert packet['plan_memory']['entries'][0]['plan']['resolution'] == 'Ivo received and read the letter.'
