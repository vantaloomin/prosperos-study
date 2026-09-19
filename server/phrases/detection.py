"""Deterministic phrase matches with offsets into unchanged original text."""
import hashlib
import re
import unicodedata
from bisect import bisect_right
from collections import Counter, defaultdict

from server.memory.cache import memoized

ALGORITHM = 'phrases-v1'
MIN_WORDS = 3
MAX_WORDS = 8
MAX_FINDINGS = 30
MAX_EVIDENCE = 8
WORDS = re.compile(r"[^\W_]+(?:[\u0300-\u036f]+[^\W_]*)*(?:['’\-][^\W_]+(?:[\u0300-\u036f]+[^\W_]*)*)*", re.UNICODE)
BOUNDARY = re.compile(r'[.!?;:\n\r]')
# Keep these words in matches; only suppress phrases made entirely of common words.
COMMON = frozenset('a an and are as at be been being but by did do does for from had has '
                   'have he her hers him his i if in into is it its me my of on or our she '
                   'so that the their them then there these they this those to too us was '
                   'we were what when where which who will with would you your said says'.split())


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@memoized('phrase-tokens-v1', 16 * 1024 * 1024)
def tokens(node_id, text):
    """Normalize each token, retaining code-point offsets and sentence boundaries."""
    result, segment, previous = [], 0, 0
    for match in WORDS.finditer(text):
        if BOUNDARY.search(text[previous:match.start()]):
            segment += 1
        word = unicodedata.normalize('NFKC', match.group()).casefold().replace('’', "'")
        result.append((word, match.start(), match.end(), segment))
        previous = match.end()
    return tuple(result)


def windows(words):
    for start in range(len(words)):
        for size in range(MIN_WORDS, min(MAX_WORDS, len(words) - start) + 1):
            end = start + size - 1
            if words[start][3] != words[end][3]:
                break
            phrase = tuple(word[0] for word in words[start:end + 1])
            if not all(word in COMMON for word in phrase):
                yield phrase, words[start][1], words[end][2]


def occurrences(passages, minimum):
    counts = Counter(phrase for node in passages for phrase, _, _ in windows(tokens(node['id'], node['text'])))
    repeated = {phrase for phrase, count in counts.items() if count >= minimum}
    matches = defaultdict(list)
    for index, node in enumerate(passages):
        ends = {}
        for phrase, start, end in windows(tokens(node['id'], node['text'])):
            if phrase in repeated and start >= ends.get(phrase, 0):
                matches[phrase].append((index, start, end))
                ends[phrase] = end
    return {phrase: spans for phrase, spans in matches.items() if len(spans) >= minimum}


def overlaps(span, covered):
    index, start, end = span
    ranges = covered[index]
    position = max(0, bisect_right(ranges, (start, end)) - 1)
    while position < len(ranges) and ranges[position][0] < end:
        left, right = ranges[position]
        if min(end, right) - max(start, left) > (end - start) / 2:
            return True
        position += 1
    return False


def cover(spans, covered):
    additions = defaultdict(list)
    for index, start, end in spans:
        additions[index].append((start, end))
    for index, ranges in additions.items():
        merged = []
        for start, end in sorted([*covered[index], *ranges]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        covered[index] = merged


def evidence(node, index, start, end):
    text = node['text']
    return {'node_id': node['id'], 'passage': index + 1, 'role': node['role'],
            'start': start, 'end': end, 'quote': text[start:end],
            'before': text[max(0, start - 90):start], 'after': text[end:end + 90],
            'more_before': start > 90, 'more_after': end + 90 < len(text),
            'sha256': digest(text)}


def finding(phrase, spans, passages):
    canonical = ' '.join(phrase)
    phrase_id = digest(ALGORITHM + ':' + canonical)
    identity = '|'.join(f'{passages[index]["id"]}:{start}:{end}' for index, start, end in spans)
    selected = spans if len(spans) <= MAX_EVIDENCE else [*spans[:2], *spans[-(MAX_EVIDENCE - 2):]]
    return {'id': digest(phrase_id + ':' + identity), 'phrase_id': phrase_id,
            'phrase': canonical, 'words': len(phrase), 'count': len(spans),
            'passage_count': len({span[0] for span in spans}),
            'evidence': [evidence(passages[index], index, start, end) for index, start, end in selected],
            'omitted_evidence': len(spans) - len(selected)}


def detect(passages, minimum=3):
    matches = occurrences(passages, minimum)
    ranked = sorted(matches, key=lambda phrase: (-len(matches[phrase]) * len(phrase), -len(phrase), phrase))
    covered, findings = defaultdict(list), []
    for phrase in ranked:
        spans = matches[phrase]
        if sum(not overlaps(span, covered) for span in spans) < minimum:
            continue
        if len(findings) == MAX_FINDINGS:
            return findings, True
        findings.append(finding(phrase, spans, passages))
        cover(spans, covered)
    return findings, False
