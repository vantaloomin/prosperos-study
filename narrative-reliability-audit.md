# Narrative reliability consolidation audit

Branch: `codex/v0.7.5-memory`. This is a local implementation and evaluation record, not a release or a claim of dependable novel-length continuity.

## What changed

1. Recall v5 protects relevant query hits already present in context while adding other evidence. On the frozen literature packets, final evidence coverage improved from 20/34 to 27/34 groups for lexical recall and from 22/34 to 28/34 for fusion, without increasing allowances. Fourteen historical v4 receipts replayed with identical writer bytes.
2. The explicit Nomic embedding input format separates document and query prefixes and cache identities. Plain-input profiles retain their previous behavior.
3. Completed, unaccepted drafts now offer **Revise continuity**. The author supplies a suspected mismatch; one additional writer request proposes another telling using the original draft, its exact permitted evidence and saved profile. The original stays available. No new search, automatic checker, acceptance gate, plan update or accepted-prose rewrite is added. A mistaken concern can be declined by returning the original.

The revision action is a fallible writing aid. Its practical gain is a way to request a targeted correction and compare it with the original without reconstructing context or losing the draft. It does not automatically detect or reliably repair every continuity fault. Manual feedback is an explicit intervention, not evidence of a reduced curation burden.

Requests exceeding the saved profile's allowance fail before creating a candidate or making a model call; sources are not silently dropped. Revision protocol v1 freezes prompt, content, source draft hash/attempt, concern and accounting. Cancellation preserves partial alternatives, retries preserve those exact inputs, and stale proposals can only be kept on a new branch. Character-limited requests retain the original permitted context. Phrase cleanup is not added to this separately requested revision. Archive v36 reconstructs and validates revision requests and source ownership; older request protocols stay unchanged.

## Evaluation coverage

The [first evaluation](narrative-reliability-evaluation.md) and [follow-up](narrative-reliability-followup.md) preserve earlier methods, costs and negative results. They include 132 paired drafts from two local writers; four real-prose retrieval fixtures; live semantic embeddings; a 104,506-word collection for cache/storage scaling; and eight real writing-loop continuations across an 18,365-word play prefix and an earlier fork. Retrieval scale and continuation reliability were measured separately. Mechanical acceptance in the disposable trajectory was a test policy, not proof that author corrections are unnecessary.

The final pass adds these completed live experiments using the already loaded Ateron model, thinking off, temperature zero:

| Experiment | Calls | Reported input tokens | Reported output tokens | Wall seconds |
|---|---:|---:|---:|---:|
| Whole-draft editor after earlier checker | 7 | 12,064 | 1,690 | 46.324 |
| Unseen contrasts and manuscript checker | 20 | 62,068 | 782 | 54.458 |
| Production revision protocol with explicit feedback | 19 | 16,151 | 2,000 | 71.483 |

The whole-draft editor used an 8,192-token context and 768-token output ceiling. It corrected dependent box references and actor/knowledge errors that the span editor left behind, but still obeyed a faulty withdrawal warning and retained unrelated unsupported details. It remains an offline experiment.

The checker saw six new authored flawed/control pairs plus the eight existing manuscript continuations, with full original evidence and a separately declared 10,240-token review allowance, 512 output tokens. It flagged all six deliberately faulty short drafts and none of their clean counterparts. In the manuscript samples, it rejected a character's conditional speculation as unsupported knowledge, and another warning confused a delivered letter with a read letter and failed exact quotation validation. It did not establish that the manuscript's other outputs were correct. This supports keeping the automatic checker experimental.

The production-protocol experiment used the exact request builder and prompt, complete frozen source contexts, a fixed generic writer-style instruction, a 10,240-token context and 768-token output ceiling. It made one proposal for each new flawed/control draft and the seven earlier flagged drafts. This is not a comparison of free-running ordinary writers: feedback was supplied explicitly, including a deliberately questionable concern on one clean control. Labels stayed outside model inputs.

Observed proposal behavior:

- All six short clean controls were returned byte-for-byte unchanged, including the false concern that remembering a withdrawn promise revived it.
- The signed-receipt contradiction was corrected; the invented porter history was replaced with a new on-page pocket check; competing testimony stayed unresolved.
- The unsent-warning revision removed the invented prior reading, but still used ambiguous "should have received" language. The hidden-sale revision changed certainty to "must have" and still let it govern the character's decision. That is not an adequate knowledge correction.
- The withdrawn-work revision corrected the obligation but introduced an unsupported statement that repairs had already begun. It is not a wholly clean revision.
- The six earlier drafts with clear targeted problems received useful corrections to fabricated reports, reversed obligation, narrator/character knowledge, object presence or claim attribution. Other original weaknesses remained, including the depot damage check and warehouse glove continuity. Correcting the flagged claim does not certify the whole draft.
- The disputed withdrawal concern still caused deletion of a legitimate memory in the longer development draft. The clean short control's success did not generalize to that sample.

Every returned proposal and checker finding was reviewed by the implementation agent. This was not blind review or an independent human assessment; the cases are enriched diagnostic samples, not an error-prevalence study. The revision stage has one-model, one-proposal-per-case evidence. More reasoning, extra reading notes and generic guidance had mixed results in earlier trials and were not made ordinary-writing defaults.

Across consolidation, completed live work totals **288 text-generation calls and 105 embedding calls: 393 inference calls**. Controlled providers, packing replay and automated tests are excluded. Reported provider token usage and workstation times are observations, not portable benchmarks. No personal profile, manuscript or loaded model configuration was changed; OpenRouter was not retried after its earlier credential failure.

## Verification

The final focused revision, scheduling and cleanup run passed **45 tests**. A preceding revision, generation recovery, recall packing and character-scope run passed **37 tests**. Coverage includes original preservation, explicit acceptance, idempotency, stale fork acceptance, hash/attempt rejection, budget refusal, cancellation, exact retry/alternative input bytes, restored source IDs, tampered archive rejection, permitted character evidence and reuse of completed recall without a second search.

Frontend model tests passed **94/94**. Ruff, ESLint, TypeScript and the production build passed. Controlled browser checks exercised the new request/result/original-comparison flow at 1440x1000 and 390x844, with zero horizontal overflow and no console warnings/errors. Screenshots exposed a narrow inline textarea; it was changed to the existing full-width field layout and the flow rerun. These browser results use an explicitly labeled disposable provider, not live semantic-quality evidence. Browser plugin was unavailable; bundled Playwright was used.

The full backend run completed with **1,255 passed and one failed** in 940.09 seconds, with two dependency deprecation warnings. The failure was `test_assessment_and_prepared_chance_preserve_summary_receipts`: its fixed assessed beat raised estimated input plus margin to 7,685 against a 7,680-token allowance, so production correctly refused it. The receipt-replay fixture now leaves 128 additional context tokens while still requiring summary selection; production limits were not relaxed. The complete summary-context, assessment and revision subset then passed **61 tests** in 67.92 seconds. The full suite was not repeated after that fixture adjustment. The small revision-timing adjustment is also covered by the final focused runs; it starts a new request clock instead of inheriting the original draft's old timestamp.

## Reproduction and preserved artifacts

New repository entry points:

- `python -m scripts.narrative_revision_evaluation --help`: local-span and whole-draft protocols.
- `python -m scripts.narrative_review_holdout --help`: authored contrasts and exact manuscript inputs.
- `python -m scripts.narrative_feedback_evaluation --help`: production request-builder evaluation.
- `python -m pytest tests/test_continuity_revision.py`: deterministic lifecycle, scope and archive checks.

Live execution requires explicit fixture/output/model arguments and a fresh output directory. Raw reports retain their `completed_unreviewed` status; this audit and the separate adjudication artifact contain subsequent review, without rewriting raw evidence.

Artifacts are under `C:/Users/Jim/.codex/visualizations/2026/09/19/01a0b7b5-8808-74e3-b54e-6b62ea00d044/`: `narrative-whole-revision-{fixture,live}-01`, `narrative-review-holdout-{fixture,live}-01`, `narrative-feedback-{fixture,live}-01`, `narrative-consolidation-final-adjudication-01.json`, and `continuity-revision-qa.json` with desktop/mobile screenshots. Earlier artifacts remain linked in the first two evaluation documents.

## Remaining limits

No automatic intervention tested here earned promotion as a dependable continuity checker or repairer. The ordinary writer can still misuse complete evidence. Manual revision is useful on specific observed failures and remains capable of new mistakes. The author retains the choice of either draft; nothing labels a revision as verified.

Full-novel continuation, larger context-pressure distributions, diverse original manuscripts, stronger multi-model replication of the revision stage, and measured human correction burden remain unproven. The current architecture and optional aid have concrete local evidence; a broad long-form reliability claim still does not.
