"""Gold evidence coverage, never a judge of generated narrative or abstention."""
import statistics

from scripts.memory_quality_metrics import covered, overlaps


def evidence_coverage(probe, ranges):
    groups = probe['evidence']
    found = [any(all(covered(target, ranges) for target in alternative) for alternative in group)
             for group in groups]
    targets = [target for group in groups for alternative in group for target in alternative]
    relevant = sum(any(overlaps(target, row) for target in targets) for row in ranges)
    return {'answerable': bool(groups), 'expected_groups': len(groups), 'found_groups': sum(found),
            'any_evidence': any(found), 'complete_evidence': bool(groups) and all(found),
            'missing_groups': [index for index, present in enumerate(found) if not present],
            'selected_ranges': len(ranges),
            'gold_range_precision': relevant / len(ranges) if groups and ranges else None}


def aggregate(rows):
    costs = [row['estimated_input_tokens'] for row in rows if 'estimated_input_tokens' in row and row['fits']]
    precision = [row['gold_range_precision'] for row in rows if row['gold_range_precision'] is not None]
    return {'probes': len(rows), 'answerable': sum(row['answerable'] for row in rows),
            'unknown': sum(not row['answerable'] for row in rows),
            'any_evidence': sum(row['any_evidence'] for row in rows),
            'complete_evidence': sum(row['complete_evidence'] for row in rows),
            'expected_groups': sum(row['expected_groups'] for row in rows),
            'found_groups': sum(row['found_groups'] for row in rows),
            'unknown_with_selected_text': sum(not row['answerable'] and bool(row['selected_ranges']) for row in rows),
            'mean_gold_range_precision': round(statistics.mean(precision), 4) if precision else None,
            'mean_estimated_input_tokens': round(statistics.mean(costs), 3) if costs else None}
