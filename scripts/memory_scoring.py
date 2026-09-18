"""Explicit benchmark scorers; no production defaults are changed."""
from server.memory.retrieval import Corpus, Hit


def raw_bm25(corpus, index, matched):
    frequency = corpus.frequencies[index]
    return sum(corpus.bm25(term, frequency[term], corpus.lengths[index]) for term in matched)


class RawBM25Corpus(Corpus):
    def score(self, index, query, query_norm, cosine_only=False):
        matched = tuple(sorted(query.keys() & self.frequencies[index].keys()))
        return Hit(self.chunks[index], raw_bm25(self, index, matched), matched)


class TFIDFCorpus(Corpus):
    def score(self, index, query, query_norm, cosine_only=False):
        return super().score(index, query, query_norm, cosine_only=True)


class RawProductCorpus(Corpus):
    def score(self, index, query, query_norm, cosine_only=False):
        cosine = super().score(index, query, query_norm, cosine_only=True)
        return Hit(cosine.chunk, cosine.score * raw_bm25(self, index, cosine.matched), cosine.matched)


SCORERS = {'tfidf': TFIDFCorpus, 'bm25': RawBM25Corpus,
           'raw_product': RawProductCorpus, 'bounded_product': Corpus}
