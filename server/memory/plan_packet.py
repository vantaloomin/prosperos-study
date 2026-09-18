"""Bounded current intentions with source excerpts; no generation or inferred transitions."""
from server.memory.budget import token_estimate
from server.memory.retrieval import terms

PLAN_RULE = (
    'These are recorded plans and commitments, not completed events or character knowledge grants. '
    'Respect each participant separately. Attempts and elapsed time do not complete a plan. '
    'If a reference could identify several plans, preserve that ambiguity. '
    'Omitted plans still exist; missing context does not prove cancellation or a unique referent. '
    'Quoted excerpts may be partial; full sources and change history remain in the story archive.'
)


def compact_plan(entry):
    evidence = [{'source_id': item['source_id'], 'quote': item['quote'][:600],
                 'partial': len(item['quote']) > 600} for item in entry['evidence'][:2]]
    return {key: entry[key] for key in ('id', 'subject', 'text', 'plan')} | {
        'evidence': evidence, 'other_evidence_count': max(0, len(entry['evidence']) - 2)}


def plan_order(entries, context):
    recent = context['history'][-1]['text'] if context['history'] else ''
    query = set(terms(context['direction'] + ' ' + recent))
    positions = {node['id']: index for index, node in enumerate(context['history'])}

    def priority(entry):
        words = set(terms(entry['subject'] + ' ' + entry['text'] + ' ' + entry['plan']['timing']))
        overlap = len(query & words)
        return (bool(overlap), overlap, entry['status'] == 'active', positions.get(entry['node_id'], -1))

    return sorted(entries, key=priority, reverse=True)


def add_plans(context, packet, prompt, target):
    entries = context.get('continuity', {}).get('entries', [])
    plans = [entry for entry in entries if entry['kind'] == 'plan']
    if not plans:
        return
    packet['continuity'] = {'entries': [entry for entry in entries if entry['kind'] != 'plan']}
    layer = {'rule': PLAN_RULE, 'entries': [], 'omitted_count': len(plans)}
    packet['plan_memory'] = layer
    initial = token_estimate(prompt, packet)
    allowance = min(1800, max(0, target - initial) * 0.35)
    for entry in plan_order(plans, context):
        trial = {**layer, 'entries': [*layer['entries'], compact_plan(entry)],
                 'omitted_count': layer['omitted_count'] - 1}
        if token_estimate(prompt, {**packet, 'plan_memory': trial}) <= initial + allowance:
            layer = trial
    packet['plan_memory'] = layer


def plan_receipt(context, packet):
    layer = packet.get('plan_memory')
    if layer is None:
        return {}
    selected = [entry['id'] for entry in layer['entries']]
    available = [entry['id'] for entry in context['continuity']['entries'] if entry['kind'] == 'plan']
    return {'plans': {'version': 1, 'available': len(available), 'selected_ids': selected,
                      'omitted_ids': [entry_id for entry_id in available if entry_id not in selected]}}
