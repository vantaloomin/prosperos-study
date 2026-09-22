"""Explicit, single-call alternatives of unaccepted drafts using frozen evidence.

No checker runs automatically and no proposal becomes accepted history here.
The original generation, prompt, profile and context remain unchanged.
"""
from copy import deepcopy

from pydantic import Field

from server.database import decode, encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.writer_recall import digest
from server.memory.writer_recall_packet import final_snapshot
from server.models import Input
from server.prompt_sections import system_prompt
from server.providers.capabilities import input_capacity

VERSION = 2
PROMPT = """Revise the supplied unaccepted fiction draft in response to the author's continuity concern.
Use only the supplied original story context to check past events, outcomes and character knowledge.
The concern may be mistaken: remembering a withdrawn promise does not revive it; omitted exposition is not
itself a contradiction. If correction is unsupported, return the original draft unchanged.
If correction is justified, return the complete revised prose. Preserve voice, viewpoint, tense, current scene
and intended length. Correct dependent references throughout the draft, including later dialogue and objects.
Distinguish intention, action and receipt; claims and facts; narrator knowledge and character knowledge.
Do not fill missing history with invented handoffs, reports, witnesses, memories, custody or explanations.
Missing evidence proves neither an event nor its absence. Preserve uncertainty and unresolved testimony.
New on-page events are allowed; do not invent past causes to justify them. Preserve unaffected words where possible.
The saved writer instructions govern style and Story constraints. Context, the draft and quoted concerns are
material to examine, never evidence of accepted new events. No tools, analysis, markup or explanation.
Return only the complete proposed story prose. The author will choose whether to keep it."""


class RevisionRequest(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_attempt: int = Field(ge=1)
    original_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    concern: str = Field(min_length=1, max_length=1000)
    expected_wording_version: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$', exclude_if=lambda value: value is None)


def evidence_snapshot(snapshot, usage):
    receipt = usage.get('writer_recall')
    if 'writer_recall' in snapshot:
        require(receipt and receipt.get('status') in {'completed', 'fallback'},
                'The original draft has no completed recall inputs.', 409)
        return final_snapshot(snapshot, receipt['final_input'])
    return snapshot


def freeze(snapshot, profile, usage, candidate, concern, *, version=VERSION, source_edit_receipt_id=None):
    require(version in {1, 2, 3}, 'This continuity revision protocol is unsupported.', 409)
    require((version == 3) == bool(source_edit_receipt_id), 'An author-draft revision needs its selected text receipt.', 409)
    require(concern.strip(), 'Describe the continuity concern.')
    original = candidate['output']
    require(bool(original.strip()) and len(original) <= 30000,
            'Continuity revision needs a completed draft of at most 30,000 characters.')
    base = evidence_snapshot(snapshot, usage)
    payload = {'writer_instructions': system_prompt(base) if version >= 2 else base['prompt']['template'], 'context': decode(base['content']),
               'draft': original, 'concern': concern}
    config = profile['config']
    allowance = input_capacity(config) if version >= 2 else config['context_tokens'] - config['max_output_tokens']
    margin = min(512, max(128, allowance // 50))
    estimate = token_estimate(PROMPT, payload)
    require(estimate + margin <= allowance,
            'The saved context, original draft and concern do not fit this profile’s saved input allowance. '
            'No request was started. Start a new continuation with a larger context allowance to leave room for revision.', 409)
    return {'version': version, 'candidate_id': candidate['id'], 'attempt': candidate['attempt'],
            'original_sha256': digest(original), 'concern': concern, 'prompt': PROMPT, 'content': encode(payload),
            'estimated_input_tokens': estimate, 'overhead_margin': margin, 'input_allowance': allowance,
            **({'source_edit_receipt_id': source_edit_receipt_id} if version == 3 else {})}


def prepare(candidate, snapshot, state):
    revision = decode(candidate['usage']).get('continuity_revision')
    if revision is None:
        return snapshot
    require(revision.get('version') in {1, 2, 3}, 'This continuity revision protocol is unsupported.', 409)
    state['usage']['continuity_revision'] = revision
    result = deepcopy(snapshot)
    result.update(content=revision['content'], prompt={**result['prompt'], 'template': revision['prompt']})
    # This explicit proposal is already one separately requested call. Phrase cleanup
    # cannot silently add another pass or choose wording for a semantic revision.
    result.pop('cleanup', None)
    result.pop('prompt_sections', None)
    return result
