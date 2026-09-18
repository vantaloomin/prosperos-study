"""The evaluation must fail honestly; these verify metrics, not a ranker's labels."""
from copy import deepcopy

import pytest

from scripts.memory_ablation import PROMPT, evaluate_probe, fixture, probe_context, reviewed_aids
from scripts.memory_quality_metrics import covered, measure_evidence, summarize
from scripts.memory_quality_variants import assemble_variant
from server.memory.chunks import compile_chunks
from server.memory.recall import current_query, latest_query
from server.memory.retrieval import Corpus


def test_fixture_has_valid_independent_labels_and_distinct_challenge_categories():
    sources, probes, fingerprint = fixture()
    assert len(fingerprint) == 64
    assert len(probes) == 84
    assert sum(bool(row['expected']) for row in probes) == 68
    features = {feature for probe in probes for feature in probe['features']}
    assert {'negation', 'rumor', 'paired_evidence', 'old_promise', 'reviewed_alias', 'reviewed_summary',
            'long_passage', 'unicode', 'non_english', 'unanswerable_overlap', 'withheld_knowledge'} <= features
    assert len({row['id'] for row in sources}) == len(sources)


def test_metric_requires_exact_evidence_not_just_the_right_source_id():
    originals = {'long': 'An unrelated beginning. The key is under the rug.'}
    probe = {'id': 'where', 'expected': [{'source_id': 'long', 'quote': 'The key is under the rug.'}]}
    chunk = compile_chunks('message:long', '', 'An unrelated beginning. ')[0]
    result = measure_evidence({'history': [], 'recalled_passages': [chunk.evidence()]}, None, probe, originals, True)
    assert not result['any_evidence'] and not result['complete_evidence']
    assert result['relevant_optional_chunks'] == 0


def test_metric_keeps_partial_multi_passage_answer_separate_from_complete_evidence():
    originals = {'rumor': 'The witness accused Sol.', 'correction': 'The witness retracted it.'}
    probe = {'id': 'accounts', 'expected': [{'source_id': key, 'quote': text} for key, text in originals.items()]}
    packet = {'history': [{'id': 'rumor', 'text': originals['rumor']}]}
    result = measure_evidence(packet, None, probe, originals, True)
    assert result['any_evidence'] and not result['complete_evidence']
    assert result['found_units'] == 1 and result['expected_units'] == 2
    blocked = measure_evidence(packet, None, probe, originals, False)
    assert blocked['found_units'] == 0 and blocked['selected_sources'] == []


def test_exact_coverage_joins_adjacent_ranges_but_not_gaps_or_other_sources():
    target = {'source_id': 'a', 'start': 8, 'end': 20}
    before = {'source_id': 'a', 'start': 0, 'end': 12}
    after = {'source_id': 'a', 'start': 12, 'end': 24}
    assert covered(target, [after, before])
    assert not covered(target, [before, {**after, 'start': 13}])
    assert not covered(target, [before, {**after, 'source_id': 'b'}])


def test_measurement_rejects_tampered_original_bytes():
    originals = {'a': 'An exact quoted passage.'}
    probe = {'id': 'quote', 'expected': [{'source_id': 'a', 'quote': originals['a']}]}
    chunk = compile_chunks('message:a', '', originals['a'])[0].evidence()
    with pytest.raises(ValueError, match='quote, range or hash'):
        measure_evidence({'history': [], 'recalled_passages': [{**chunk, 'sha256': 'wrong'}]}, None,
                         probe, originals, True)


def test_ablations_preserve_inputs_and_restore_production_functions():
    sources, probes, _ = fixture()
    context = probe_context(sources, probes[0])
    aids = reviewed_aids(sources)
    preserved = deepcopy((context, aids))
    profile = {'config': {'context_tokens': 4096, 'max_output_tokens': 512}}
    from server.memory import recall
    for variant in ('bm25', 'cosine', 'no_recent_query', 'no_latest_query', 'no_aliases', 'no_summaries', 'no_threads'):
        assemble_variant(context, PROMPT, profile, aids, variant)
        assert (context, aids) == preserved
        assert recall.Corpus is Corpus and recall.current_query is current_query
        assert recall.latest_query is latest_query


def test_full_history_cannot_pass_the_gate_by_exceeding_the_same_budget():
    sources, probes, _ = fixture()
    aids = reviewed_aids(sources)
    small = evaluate_probe(sources, probes[0], aids, 'full_history', 4096)
    large = evaluate_probe(sources, probes[0], aids, 'full_history', 65536)
    assert not small['fits'] and not small['any_evidence']
    assert large['fits'] and large['complete_evidence']


def test_missing_answer_and_no_optional_recall_have_truthful_denominators():
    sources, probes, _ = fixture()
    absent = next(probe for probe in probes if probe['id'] == 'm-absent-overlap')
    row = evaluate_probe(sources, absent, reviewed_aids(sources), 'adapted', 4096)
    report = summarize([row])
    assert report['answerable'] == 0 and report['unanswerable'] == 1
    assert report['mean_optional_evidence_precision'] is None
    assert report['complete_evidence'] == 0
    assert not row['missing']  # No asserted answer, rather than a fabricated expected source.


def test_same_frozen_fixture_produces_identical_evidence_and_cost_records():
    sources, probes, _ = fixture()
    aids = reviewed_aids(sources)
    probe = next(row for row in probes if row['id'] == 'm-summary')
    first = evaluate_probe(sources, probe, aids, 'adapted', 4096)
    assert first == evaluate_probe(sources, probe, aids, 'adapted', 4096)


@pytest.mark.parametrize('budget', [4096, 8192])
def test_latest_scene_clue_survives_repetitive_preceding_prose(budget):
    sources, probes, _ = fixture()
    aids = reviewed_aids(sources)
    probe = next(row for row in probes if row['id'] == 'recent-cue')
    improved = evaluate_probe(sources, probe, aids, 'adapted', budget)
    previous = evaluate_probe(sources, probe, aids, 'no_latest_query', budget)
    assert improved['fits'] and improved['complete_evidence']
    assert not previous['any_evidence']


def test_latest_clue_cannot_reintroduce_an_explicitly_excluded_source():
    sources, probes, _ = fixture()
    probe = next(row for row in probes if row['id'] == 'recent-cue')
    context = probe_context(sources, probe)
    target = next(source for source in sources if source['id'] == 'talisman')
    chunk = compile_chunks('message:talisman', 'narrator passage', target['text'])[0]
    context['author_memory'] = {'entries': [{'kind': 'emphasis', 'stance': 'exclude',
                               'sources': [{'id': chunk.id, 'node_id': 'talisman'}]}]}
    profile = {'config': {'context_tokens': 4096, 'max_output_tokens': 512}}
    packet, _ = assemble_variant(context, PROMPT, profile, reviewed_aids(sources), 'adapted')
    assert all(node['id'] != 'talisman' for node in packet['history'])
    assert all(row['source_id'] != 'message:talisman' for row in packet['recalled_passages'])


def test_latest_query_uses_accepted_prose_past_author_notes():
    context = {'history': [{'role': 'narrator', 'text': 'The verdigris talisman was on the table.'},
                           {'role': 'ooc', 'text': 'Do not reveal the author’s private solution.'}]}
    assert latest_query(context) == context['history'][0]['text']
    assert latest_query({'history': context['history'][1:]}) == ''
