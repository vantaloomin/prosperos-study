"""Independent lexical scoring; statistics only see the caller's eligible corpus."""
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from server.memory.cache import memoized
from server.memory.chunks import Chunk
from server.memory.index_format import load_counts

WORDS = re.compile(r"[^\W_]+(?:['\u2019\-][^\W_]+)*", re.UNICODE)
STOP = frozenset('a about an and are as at be been being but by for from had has have he her '
                 'hers him his i if in into is it its me my of on or our she so than '
                 'that the their them then there these they this those to was we were '
                 'what when where which who will with would you your continue story'.split())


def token_stream(text):
    normalized = unicodedata.normalize('NFKC', text).casefold().replace('\u2019', "'")
    return (match.group() for match in WORDS.finditer(normalized) if match.group() not in STOP)


@memoized('terms-v3', 4 * 1024 * 1024)
def terms(text):
    return tuple(token_stream(text))


@memoized('term-counts-v3', 16 * 1024 * 1024, dump=list, load=load_counts)
def term_counts(text):
    return tuple(Counter(token_stream(text)).items())


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    matched: tuple[str, ...]
    reason: str = 'Related to the current passage or direction'
    anchor_id: str | None = None


class Corpus:
    def __init__(self, chunks):
        self.chunks = tuple(chunks)
        self.frequencies = [dict(term_counts(' '.join((c.text, c.title, *c.aliases)))) for c in self.chunks]
        self.df = Counter(term for frequency in self.frequencies for term in frequency)
        self.lengths = [sum(frequency.values()) for frequency in self.frequencies]
        self.average = sum(self.lengths) / max(len(self.lengths), 1)
        self.idf = {term: math.log((len(self.chunks) + 1) / (count + 1)) + 1
                    for term, count in self.df.items()}
        self.norms = [math.sqrt(sum((count * self.idf[term]) ** 2 for term, count in frequency.items()))
                      for frequency in self.frequencies]

    def search(self, query, limit=16, threshold=0.01, *, cosine_only=False):
        query_counts = Counter(terms(query))
        if not query_counts.keys() & self.df.keys():
            return []
        unseen_idf = math.log(len(self.chunks) + 1) + 1
        query_norm = math.sqrt(sum((count * self.idf.get(term, unseen_idf)) ** 2
                                   for term, count in query_counts.items()))
        if not query_norm:
            return []
        hits = [self.score(index, query_counts, query_norm, cosine_only) for index in range(len(self.chunks))]
        return sorted((hit for hit in hits if hit.score >= threshold),
                      key=lambda hit: (-hit.score, hit.chunk.source_id, hit.chunk.start))[:limit]

    def score(self, index, query, query_norm, cosine_only=False):
        frequency = self.frequencies[index]
        matched = tuple(sorted(query.keys() & frequency.keys()))
        dot = sum(query[term] * frequency[term] * self.idf[term] ** 2 for term in matched)
        cosine = dot / max(query_norm * self.norms[index], 1e-12)
        if cosine_only:
            return Hit(self.chunks[index], cosine, matched)
        raw = sum(self.bm25(term, frequency[term], self.lengths[index]) for term in matched)
        scale = math.log(1 + (len(self.chunks) - 0.5) / 1.5) if self.chunks else 1
        normalized = 1 - math.exp(-raw / max(scale, 1))
        return Hit(self.chunks[index], cosine * normalized, matched)

    def bm25(self, term, count, length):
        rarity = math.log(1 + (len(self.chunks) - self.df[term] + 0.5) / (self.df[term] + 0.5))
        divisor = count + 1.2 * (0.25 + 0.75 * length / max(self.average, 1))
        return rarity * count * 2.2 / divisor
