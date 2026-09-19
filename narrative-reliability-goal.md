# Narrative reliability consolidation goal

Work on `codex/v0.7.5-memory`, preserving all existing v0.7.5 changes. This goal starts from the completed enhanced-memory implementation; it does not authorize release or publication.

## Outcome

Improve how ordinary writing uses retrieved evidence: preserve established outcomes, distinguish intention from action and receipt, keep testimony uncertain when unverified, and avoid inventing past events or character knowledge to fill gaps. Retain creative freedom to write new events after the current story point. Measure reliability separately from retrieval coverage and establish practical manuscript-scale costs.

The previous seven-case live comparison supplied all 19 required permitted passages with linked recall, yet produced omissions, unsupported handoffs/knowledge and an earlier-fork regression. That result is the starting evidence, not a claim that retrieval or prose is solved.

## Work and acceptance

- [x] Freeze regression inputs and a narrative rubric before new scored runs. Cover the seven existing cases, including failed/successful siblings, names/pronouns, withdrawal, testimony, exclusion and the earlier fork. Preserve negative outputs. Separate absent evidence, ignored evidence, contradictions, unsupported past events and unsupported knowledge; do not demand that every source sentence appear in the draft.
- [x] Evaluate a bounded intervention for the ordinary writer. Start with evidence-use guidance, then add another model stage only if measured failures justify its cost. Distinguish new creative developments from unsupported retrospective claims. Never promote annotations into accepted facts, silently rewrite accepted prose, or disclose hidden character evidence.
- [x] Keep replay and budget contracts for this pass. Existing saved requests, retries, custom prompts and Story-pinned prompts retain their original bytes. Any changed built-in behavior must be versioned; all new guidance consumes the existing allowance. Verify archive restore, character scope, fallback and accepted-state preservation with meaningful focused checks. Recheck these contracts before promoting a later intervention.
- [x] Add manuscript-scale evaluation using the existing locally preserved public-domain narrative corpus and frozen evidence labels, plus controlled branch/knowledge regressions. Report actual source sizes, cold/warm retrieval time, stored snapshot/cache sizes and warming costs. Do not manufacture scale by repeating one filler paragraph and call that realistic prose. This first pass tests retrieval/scale; manuscript continuation remains below.
- [x] Run paired repeated live writing comparisons with fixed input evidence and equal profile allowances, retaining exact inputs, model identity, outputs, calls/tokens and time. Include fresh narrative cases alongside development regressions. Review without turning model self-scores or keyword matches into factual correctness. Use additional authorized models where available and state the limits of any one-model result.
- [x] Evaluate optional semantic retrieval with an explicitly selected suitable embedding model, separately from writer quality: lexical versus independent semantic versus fusion, cold-cache fallback, warm-cache evidence and cost. Do not use a writing model as an embedder or infer quality from synthetic vectors.
- [x] Publish a local completion audit with actual gains, regressions, interventions and unresolved limits. Changes without convincing evidence remain experiments rather than silently replacing production behavior.

## Evaluation policy

The narrative rubric is fixed before candidate comparison: (1) consistency with established outcomes and withdrawals; (2) no invented retrospective action/outcome used to explain missing history; (3) no unsupported character witness, memory or certainty; (4) preserve unresolved testimony; (5) relevant causal relationships govern the scene without forcing exposition; (6) coherent, usable fiction follows the requested direction. Source coverage, prose review and aesthetic quality are distinct measurements. A narrator can know a narrated event without every character knowing it. New on-page actions are allowed; their asserted historical causes still need support.

Use equal context/output limits, record all provider calls including exploratory ones, and keep old artifacts immutable. Balance variant order across repetitions. A small paired sample supports only a local observation. Any review by the implementation agent is disclosed; no independent-human or statistically significant claim is implied. Do not select a candidate solely because it retrieves more text or passes parser tests.

## Initial state — 2026-09-19

The active branch is `codex/v0.7.5-memory` with substantial existing uncommitted work. LM Studio is reachable and currently has `ateron_gemma-4-novelist-eclipse-31b` loaded. Its local catalog also contains Nomic Embed Text v1.5 and other downloaded writers; none are silently treated as already loaded. Live work uses disposable evaluation data, not personal manuscripts or saved profiles. The earlier OpenRouter credential failure is not retried without a relevant configuration change.

First step: freeze the existing failed inputs and a bounded evidence-use guidance candidate, then compare actual drafts before changing the production writer.

## First pass completed; goal remains active

See [the measured evaluation](narrative-reliability-evaluation.md). Eleven cases, two local writers and three paired repetitions produced 132 drafts; 16 subsequent checker calls tested selected failures and clean controls. Generic guidance and a checker both remain experimental because they missed consequential faults. No production writer prompt or acceptance behavior changed.

Live Nomic tests prompted an explicit embedding input-format setting, now implemented and verified, with plain-input compatibility and separate cache identity. Four real-prose works and a 104,506-word collection establish initial retrieval, cache-warming and storage measurements. Correctly prefixed fusion supplied 22/34 required evidence groups in final packets versus 20/34 lexical, while fused candidates contained 28/34. This identifies context packing as another unresolved limit.

Next bounded work:

- [x] Explain and evaluate the candidate-to-packet evidence loss without increasing context allowances or changing frozen labels. Recall v5 protects query hits already present in context; frozen replay improves final lexical coverage from 20/34 to 27/34 and fused coverage from 22/34 to 28/34. Fourteen historical v4 live receipts retain exact writer bytes. Archive v35 preserves prior request versions.
- [x] Compare an explicit source-grounded account of events, testimony and character knowledge against the current writer. Treat any model interpretation as tentative; keep it experimental unless prose improves without unsupported-history regressions. Eleven quoted reading aids and 44 paired drafts remain experimental after mixed results. A separate 16-draft thinking off/on comparison also failed to justify a global setting change.
- [x] Extend to repeated ordinary continuations along a coherent manuscript, measuring author interventions, branch/knowledge drift and accumulating storage. Eight live continuations across an 18,365-word play prefix and an earlier fork exercised the real pipeline. Mechanical acceptance was the declared test policy, not proof that author corrections are unnecessary. Storage and output weaknesses are recorded in the follow-up; full-novel generalization remains unproven.
- [x] Evaluate bounded proposed revisions of specific flagged continuity claims, retaining the original draft and including clean controls. Do not turn an uncertain checker result into an acceptance gate or accepted story fact. Integrate only an intervention with measured usefulness and preserved scope/retry/cancellation/budget behavior. The local-span and automatic-checker approaches remain experimental. Whole-draft and explicit-feedback proposals were evaluated next; the optional author-requested revision action preserves originals, exact evidence and acceptance controls. It corrected specific observed claims and preserved six clean controls, but still produced failures. The completion audit records those limits; no automatic semantic repair or verification gate was promoted.

Acceptance still requires evidence of improved use of history. Completing infrastructure or rejecting weak candidates alone does not complete this goal.

See [the packing and manuscript follow-up](narrative-reliability-followup.md) for the second pass, compatibility evidence, 94 further inference calls, and the next writer intervention. All 1,247 backend tests passed after the production packing change. The production writer prompt remains unchanged.


## Consolidation complete

The [local completion audit](narrative-reliability-audit.md) records the implemented packing and embedding fixes, optional Revise continuity action, 393 completed inference calls, realistic manuscript/scale measurements, negative experiments and verification. Archive v36 adds validated revision-request provenance. Final affected checks passed; the full run and its corrected budget-sensitive test fixture are reported separately. No release or publication was performed.

This goal completed evidence-backed consolidation and a bounded author-controlled improvement. It did not establish dependable long-form continuity, automatic diagnosis, or freedom from unsupported history. Those limits remain explicit rather than being inferred from passing infrastructure tests.
