"""Development evidence metrics checked against separately specified exact source ranges."""
import hashlib
import math
import statistics


def expected_ranges(probe, originals):
    result = []
    for item in probe['expected']:
        text = originals[item['source_id']]
        start = text.find(item['quote'])
        if start < 0 or not item['quote']:
            raise ValueError(f"Invalid gold quote in {probe['id']}: {item['source_id']}")
        result.append({'source_id': item['source_id'], 'start': start, 'end': start + len(item['quote'])})
    return result


def exact_ranges(packet, originals):
    result = []
    for node in packet['history']:
        if originals[node['id']] != node['text']:
            raise ValueError('History bytes changed in evaluated context')
        result.append({'source_id': node['id'], 'start': 0, 'end': len(node['text'])})
    for item in packet.get('recalled_passages', []):
        source_id = item['source_id'].removeprefix('message:')
        text = originals[source_id][item['start']:item['end']]
        if text != item['text'] or hashlib.sha256(text.encode()).hexdigest() != item['sha256']:
            raise ValueError('Retrieved quote, range or hash changed')
        result.append({**item, 'source_id': source_id})
    return result


def covered(target, ranges):
    cursor = target['start']
    same_source = sorted((row for row in ranges if row['source_id'] == target['source_id']),
                         key=lambda row: row['start'])
    for row in same_source:
        if row['start'] > cursor:
            break
        cursor = max(cursor, row['end'])
        if cursor >= target['end']:
            return True
    return False


def overlaps(target, row):
    return (target['source_id'] == row['source_id'] and target['start'] < row['end']
            and row['start'] < target['end'])


def measure_evidence(packet, receipt, probe, originals, fits):
    targets = expected_ranges(probe, originals)
    ranges = exact_ranges(packet, originals) if fits else []
    optional = [row for row in ranges if 'sha256' in row]
    found = [covered(target, ranges) for target in targets]
    recalled = [covered(target, optional) for target in targets]
    # Receipt order is ranking/allocation order; packet presentation is narrative order.
    by_id = {row['id']: row for row in optional}
    ranks = [index + 1 for index, row in enumerate((receipt or {}).get('selected', []))
             if row['id'] in by_id and any(overlaps(target, by_id[row['id']]) for target in targets)]
    return {'expected_units': len(targets), 'found_units': sum(found),
            'complete_evidence': bool(targets) and all(found), 'any_evidence': any(found),
            'recall_found_units': sum(recalled), 'optional_chunks': len(optional),
            'relevant_optional_chunks': sum(any(overlaps(target, row) for target in targets) for row in optional),
            'first_expected_recall_rank': min(ranks) if ranks else None,
            'missing': [target for target, present in zip(targets, found, strict=True) if not present],
            'selected_sources': list(dict.fromkeys(row['source_id'] for row in ranges)),
            'selected_recall_ids': [row['id'] for row in (receipt or {}).get('selected', [])] if fits else []}


def distribution(values):
    if not values:
        return None
    values = sorted(values)
    return {'mean': round(statistics.mean(values), 3), 'p50': values[math.ceil(len(values) * .5) - 1],
            'p95': values[math.ceil(len(values) * .95) - 1], 'max': values[-1]}


def summarize(rows):
    answerable = [row for row in rows if row['expected_units']]
    absent = [row for row in rows if not row['expected_units']]
    precisions = [row['relevant_optional_chunks'] / row['optional_chunks'] for row in answerable
                  if row['optional_chunks']]
    return {'probes': len(rows), 'answerable': len(answerable), 'unanswerable': len(absent),
            'fits': sum(row['fits'] for row in rows),
            'any_evidence': sum(row['any_evidence'] for row in answerable),
            'complete_evidence': sum(row['complete_evidence'] for row in answerable),
            'any_evidence_rate': round(sum(row['any_evidence'] for row in answerable) / max(len(answerable), 1), 4),
            'complete_evidence_rate': round(sum(row['complete_evidence'] for row in answerable) / max(len(answerable), 1), 4),
            'expected_units': sum(row['expected_units'] for row in answerable),
            'found_units': sum(row['found_units'] for row in answerable),
            'optional_recall_hits_at_8': sum(0 < (row['first_expected_recall_rank'] or 99) <= 8 for row in answerable),
            'mean_optional_evidence_precision': round(statistics.mean(precisions), 4) if precisions else None,
            'unanswerable_with_optional_evidence': sum(bool(row['optional_chunks']) for row in absent),
            'estimated_input_tokens': distribution([row['estimated_input_tokens'] for row in rows if row['fits']])}


def grouped(rows, key):
    return {value: summarize([row for row in rows if value in row[key]])
            for value in sorted({value for row in rows for value in row[key]})}
