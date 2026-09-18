"""Compile only an explicitly supplied immutable Markdown overview.

Rule-controlled entries are intentionally separate: the lore engine, not this
compiler, decides whether they are eligible for a particular request.
"""
import hashlib
from bisect import bisect_right
from dataclasses import replace

from server.memory.canon_models import canon_policy
from server.memory.chunks import compile_chunks

COMPILER = 'prospero-markdown-v1'


def source_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def current_cues(text, policy):
    # Editing Markdown never silently reattaches a cue to a different passage.
    # Stale cues stay in the version for review, but do not enter the index.
    return [cue for cue in policy.cues if cue.end <= len(text)
            and source_digest(text[cue.start:cue.end]) == cue.sha256]


def compile_overview(source_id, name, content):
    text = content.get('text', '')
    text = text if isinstance(text, str) else ''
    policy = canon_policy(content)
    cues = current_cues(text, policy)
    boundaries = sorted({0, len(text), *(cue.start for cue in cues), *(cue.end for cue in cues)})
    by_start = {cue.start: cue for cue in cues}
    chunks = []
    for start, end in zip(boundaries, boundaries[1:]):
        cue = by_start.get(start)
        aliases = (cue.summary, *cue.topics, *cue.aliases) if cue else ()
        for chunk in compile_chunks(source_id, name, text[start:end], 'Canon reference', aliases):
            absolute_start, absolute_end = start + chunk.start, start + chunk.end
            chunks.append(replace(chunk, start=absolute_start, end=absolute_end,
                                  id=f'{source_id}@{absolute_start}:{absolute_end}:{chunk.digest[:12]}'))
    return tuple(chunks), {'compiler': COMPILER, 'source_sha256': source_digest(text),
                          'chunks': len(chunks), 'active_cues': len(cues),
                          'stale_cues': len(policy.cues) - len(cues), 'mode': policy.mode}



class CueIndex:
    def __init__(self, content):
        self.cues = sorted(current_cues(content.get('text', ''), canon_policy(content)), key=lambda cue: cue.start)
        self.starts = [cue.start for cue in self.cues]

    def fields(self, chunk):
        index = bisect_right(self.starts, chunk.start) - 1
        cue = self.cues[index] if index >= 0 else None
        if cue and chunk.end <= cue.end:
            return {'summary': cue.summary, 'topics': cue.topics, 'aliases': cue.aliases}
        return {'summary': '', 'topics': [], 'aliases': []}
