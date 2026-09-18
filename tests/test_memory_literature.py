"""Harness integrity and scorer arithmetic; no desired retrieval score is asserted."""
import json
import math

import pytest

from scripts import memory_literature_fixture as fixture
from scripts.memory_literature_evaluation import context_for, ranked_packet
from scripts.memory_literature_metrics import aggregate, evidence_coverage
from scripts.memory_quality_variants import assemble_variant
from scripts.memory_scoring import SCORERS, RawProductCorpus
from server.memory.chunks import compile_chunks
from server.memory.retrieval import Corpus


def test_verified_literature_has_all_unique_quotes_and_keeps_original_segmentation():
    stories, probes = fixture.literature_fixture()
    assert len(stories) == 4 and len(probes) == 32
    assert sum(bool(p['evidence']) for p in probes) == 24
    assert sum(len(s['sources']) for s in stories.values()) == 140
    for story in stories.values():
        assert ''.join(s['text'] for s in story['sources']) == story['text']
        assert 'END OF THE PROJECT GUTENBERG' not in story['text']
    assert all(all(alternative for alternative in group) for p in probes for group in p['evidence'])


def test_four_scorers_match_hand_computed_values_and_keep_production_class():
    chunks = (*compile_chunks('a', '', 'red red ink'), *compile_chunks('b', '', 'blue ink'))
    idf = math.log(3 / 2) + 1
    cosine = 2 * idf / math.sqrt((2 * idf) ** 2 + 1)
    bm25 = math.log(2) * 4.4 / (2 + 1.2 * (0.25 + 0.75 * 3 / 2.5))
    expected = {'tfidf': cosine, 'bm25': bm25, 'raw_product': cosine * bm25,
                'bounded_product': cosine * (1 - math.exp(-bm25))}
    for name, scorer in SCORERS.items():
        hits = scorer(chunks).search('red', threshold=1e-15)
        assert len(hits) == 1 and hits[0].chunk.source_id == 'a'
        assert hits[0].score == pytest.approx(expected[name])
        assert not scorer(chunks).search('absent')
    assert SCORERS['bounded_product'] is Corpus


def test_gold_groups_accept_alternatives_but_require_every_group_and_all_split_pieces():
    a = {'source_id': 'a', 'start': 0, 'end': 10}
    b = {'source_id': 'b', 'start': 0, 'end': 10}
    c = {'source_id': 'c', 'start': 2, 'end': 5}
    probe = {'evidence': [[[a, b], [c]], [[b]]]}
    assert evidence_coverage(probe, [b, c])['complete_evidence']
    partial = evidence_coverage(probe, [b])
    assert partial['any_evidence'] and not partial['complete_evidence']
    assert partial['missing_groups'] == [0]
    gap = [{**a, 'end': 4}, {**a, 'start': 5}, b]
    assert not evidence_coverage(probe, gap)['complete_evidence']


def test_unknowns_are_not_counted_as_passed_or_as_hallucinated_answers():
    result = evidence_coverage({'evidence': []}, [{'source_id': 'a', 'start': 0, 'end': 10}])
    report = aggregate([result])
    assert report['answerable'] == 0 and report['unknown'] == 1
    assert report['complete_evidence'] == 0 and report['unknown_with_selected_text'] == 1
    assert report['mean_gold_range_precision'] is None


def test_quote_lookup_rejects_empty_ambiguous_or_invented_gold():
    for quote in ('', 'repeated', 'invented'):
        with pytest.raises(ValueError):
            fixture.quote_range('repeated repeated', quote)
    assert fixture.quote_range('line one\n  line two', 'line one line two') == (0, 19)


def test_changed_download_is_rejected_before_retrieval(tmp_path):
    data = b'original'
    (tmp_path / 'sample.txt').write_bytes(b'modified')
    (tmp_path / 'sources.json').write_text(json.dumps({'files': [
        {'file': 'sample.txt', 'bytes': len(data), 'sha256': fixture.sha256(data)}]}), encoding='utf-8')
    with pytest.raises(ValueError, match='Original download changed'):
        fixture.source_texts(tmp_path)


def test_freeze_cannot_be_overwritten_and_detects_code_drift(tmp_path, monkeypatch):
    path = tmp_path / 'freeze.json'
    monkeypatch.setattr(fixture, 'literature_fixture', lambda: None)
    monkeypatch.setattr(fixture, 'fingerprints', lambda: {
        'tests/fixtures/long_story_literature/annotations.json': 'original', 'scorer.py': 'before'})
    fixture.freeze_fixture(path)
    assert fixture.verify_freeze(path)['annotation_sha256'] == 'original'
    with pytest.raises(FileExistsError):
        fixture.freeze_fixture(path)
    monkeypatch.setattr(fixture, 'fingerprints', lambda: {'scorer.py': 'after'})
    with pytest.raises(ValueError, match='Frozen evaluation inputs changed'):
        fixture.verify_freeze(path)


def test_ranked_budget_prefix_does_not_pull_labels_or_recent_prose_into_search():
    sources = [{'id': str(i), 'text': 'red ' * 550} for i in range(10)]
    story = {'sources': sources}
    context = context_for(story, {'query': 'red'})
    chunks = [c for source in sources for c in compile_chunks('message:' + source['id'], '', source['text'])]
    hits = Corpus(chunks).search('red', limit=10)
    packet, selected = ranked_packet(context, hits, 2048, enforce_budget=True)
    assert 0 < len(selected) < len(hits)
    assert [row['id'] for row in selected] == [hit.chunk.id for hit in hits[:len(selected)]]
    assert packet['history'] == [] and len(context['history']) == 10


def test_raw_product_writer_counterfactual_does_not_leak_patch():
    from server.memory import recall
    sources = [{'id': str(i), 'text': 'A red candle lit the stone room. ' * 30} for i in range(10)]
    context = context_for({'sources': sources}, {'query': 'red candle'})
    original = json.dumps(context, sort_keys=True)
    assemble_variant(context, 'Continue.', {'config': {'context_tokens': 4096, 'max_output_tokens': 512}},
                     {}, 'raw_product')
    assert recall.Corpus is Corpus and recall.Corpus is not RawProductCorpus
    assert json.dumps(context, sort_keys=True) == original
