from scripts.memory_evaluation import quality_report
from server.memory.chunks import compile_chunks
from server.memory.retrieval import Corpus


def test_authored_retrieval_corpus_meets_first_slice_source_recall_gate():
    report = quality_report()
    assert report['probes'] == 60
    answerable = sum(genre['answerable'] for genre in report['genres'].values())
    hits = sum(genre['hits_at_8'] for genre in report['genres'].values())
    assert hits / answerable >= 0.9, report['misses']
    assert all(genre['absent_with_hits'] == 0 for genre in report['genres'].values())


def test_retrieval_preserves_negation_and_conflicting_accounts_as_exact_evidence():
    sources = [('rumor', 'The porter claimed Vera stole the emerald. This was unverified.'),
               ('correction', 'The porter admitted he had lied: Vera did not steal the emerald.')]
    corpus = Corpus(chunk for key, text in sources for chunk in compile_chunks(key, '', text))
    hits = corpus.search('Vera emerald porter', limit=8)
    assert {hit.chunk.source_id for hit in hits} == {'rumor', 'correction'}
    assert {hit.chunk.text for hit in hits} == {text for _, text in sources}
    # Retrieval does not resolve contradictions by deleting or rewriting either account.


def test_chunked_long_passage_keeps_exact_answer_offsets_and_unknown_aliases_do_not_expand_scope():
    text = 'The room was quiet. ' * 3000 + '\n\nÉléonore placed the violet medallion beneath the piano.\n'
    corpus = Corpus(compile_chunks('allowed', '', text))
    hit = corpus.search('Éléonore violet medallion', limit=1)[0]
    assert 'violet medallion' in hit.chunk.text
    assert text[hit.chunk.start:hit.chunk.end] == hit.chunk.text
    assert corpus.search('unpublished-alias') == []
