# Narrative reliability: first consolidation pass

2026-09-19, `codex/v0.7.5-memory`. This records work under [the active goal](narrative-reliability-goal.md), not a completed reliability claim or a release.

## Decision

Keep the existing production writer prompt. An extra evidence-use instruction improved some Ateron regressions but did not consistently transfer to another writer or fresh cases. A separate draft checker caught some clear faults but missed others and overinterpreted one omission. Both remain offline experiments. The production change in this pass is explicit Nomic embedding input-format support, with separate cache identity and preserved legacy behavior.

Retrieval quality and prose correctness remain separate. Live semantic retrieval found more relevant evidence than lexical retrieval in the tested corpus, but part of that gain was lost during context packing. Neither higher coverage nor a checker returning no issues establishes correct fiction.

## Paired writing experiment

Seven previous parcel regressions reuse the exact final linked evidence from the earlier evaluation. Four additional authored cases cover confirmed receipt with a sender who has not heard, an accepted withdrawal, narrator-only knowledge, and conflicting registry testimony. The new cases are short controlled probes, not manuscript-scale writing. They were frozen before their outputs were generated, after observing the development cases. They are not an independent held-out benchmark.

Each model produced baseline and guidance variants three times per case: **132 drafts**, all read by the implementation agent. Both variants received the identical source packet and direction. The guidance only extends the system prompt; labels and review notes never enter model input. Context allowance was 4,608 tokens, output ceiling 512, temperature 0.4, reasoning off. Order alternated baseline/candidate, candidate/baseline, baseline/candidate. This is paired but not perfectly order-balanced. Seeds were not fixed. Different model tokenizers produced different actual token counts within the same allowances.

| Model and input set | Calls | Reported input tokens | Reported output tokens | Run wall seconds |
|---|---:|---:|---:|---:|
| Ateron Gemma, seven regressions | 42 | 126,372 | 8,252 | 250.863 |
| Ateron Gemma, four fresh cases | 24 | 19,896 | 4,822 | 134.179 |
| Qwen, seven regressions | 42 | 128,514 | 9,087 | 240.026 |
| Qwen, four fresh cases | 24 | 19,728 | 5,677 | 118.576 |

Exact returned model IDs were `ateron_gemma-4-novelist-eclipse-31b` and `qwen3.8-27b-uncensored`. These are local model instances, not claims about all Gemma or Qwen models. Every call completed. Raw journals retain exact prompts, packets, output, usage, actual identity and elapsed time. Raw reports remain marked `completed_unreviewed`; this separate document records the subsequent qualitative review without overwriting them.

### Observed gains and regressions

- **Earlier fork, Ateron:** all three baseline drafts invented private history or knowledge behind the missing parcel; all three guidance drafts left it unresolved. This is the clearest local gain.
- **Excluded handoff, Ateron:** guidance avoided a dispatch claim in two repetitions, but the third still said “I sent it away.” The intervention does not consistently respect absent transfer evidence.
- **Successful receipt:** guidance helped preserve receipt, but some Ateron drafts still granted the sender knowledge without a report. Receiving an object and the sender knowing about receipt are different facts.
- **Withdrawal:** some drafts did not use the accepted withdrawal in their framing. Mere omission is not automatically a contradiction: remembering an old promise can be legitimate after withdrawal. We do not count every missing recap as failure.
- **Fresh Ateron cases:** the receipt and withdrawal scenes generally allowed new disclosure and new practical choices. However, one guided registry draft invented an earlier search of the intake bins. This is a fresh-case regression, not a reason to promote the guidance.
- **Qwen parcel cases:** both variants often treated a parcel-shaped empty space as an actual parcel, confused sender/recipient roles, or supplied unsupported private knowledge. Guidance helped preserve unresolved testimony in some samples but was not a consistent fix for fork, exclusion or identity handling.
- **Fresh Qwen cases:** a guided receipt draft invented Fen's earlier report to Ada despite explicit evidence that she had received none; another reversed who owed work in the withdrawn permit. Registry drafts sometimes transferred the courier's delivery claim to Mira. Warehouse drafts sometimes gave characters narrator-only knowledge or invented an earlier keeper sighting. Several other samples handled the same distinctions correctly.

These are nonblind qualitative observations, with no independent human adjudication, statistical claim or invented aggregate prose-accuracy score. The rubric permits sensory detail, new on-page action and characters discussing uncertain beliefs. It does not permit retrospective events to be invented as established continuity. No model-produced scores were used as ground truth.

## Bounded draft-check experiment

The continued faults justified testing one additional model call, outside the application. Sixteen existing drafts were selected and frozen before checking: ten suspected problems and six intended clean controls. This deliberately enriched selection cannot estimate ordinary error prevalence or precision. The checker saw the original scoped context and draft, without labels or expected concerns, and could return at most two issues with exact draft and evidence quotations. It could not rewrite anything.

Ateron made **16 calls**, 27,883 reported input tokens and 738 output tokens, in **40.623 seconds**; median call time was **2.211 seconds**. Its context ceiling was 8,192 tokens and output ceiling 512, temperature zero. The larger allowance accommodates the existing evidence plus the draft and review instructions; this is additional cost, not an equal-cost replacement for writing.

Initially 13 responses failed strict JSON parsing because they used one outer code fence. Offline replay with the application's existing single-fence normalization validated all 16 references, with no additional inference. Raw outputs and initial failure statuses are preserved separately from `normalized-review.json`. Matching quotations establish only the references, not the correctness of the concern.

Review found **six clear faults flagged, three clear faults missed, and no flags on the six intended clean controls**. The remaining flagged sample was the withdrawal scene: the checker claimed that remembering the promise restored the obligation. That conclusion is too strong from the cited wording. The fixture's original suspected-problem label is retained, with this disagreement disclosed rather than relabeling silently. Thus seven emitted warnings must not be reported as seven confirmed catches.

Misses include the earlier-fork private knowledge, the excluded dispatch, and the invented intake-bin search. An empty issue list cannot be used as permission to accept a draft automatically. No repair calls or silent draft replacements were added.

## Real-prose retrieval and scale

The existing locally preserved public-domain corpus and evidence labels were frozen unchanged: *The Speckled Band*, *A Doll's House*, *The Machine Stops*, and *To Build a Fire*. There are **32 queries**, including **24 answerable queries with 34 required evidence groups**, and eight unknown-answer probes. Unknown probes are retained but not counted as answered correctly merely because search returns text. Retrieval uses an author view over the whole work; it is not a character-scoped or chronological continuation test.

| Corpus | Words | Characters | Frozen chunks |
|---|---:|---:|---:|
| The Speckled Band | 9,812 | 52,954 | 24 |
| A Doll's House | 26,432 | 141,928 | 62 |
| The Machine Stops | 12,162 | 68,506 | 34 |
| To Build a Fire | 7,085 | 38,130 | 20 |
| Holmes collection, scale only | 104,506 | 562,213 | 263 |

The collection tests storage and retrieval cost on real prose of manuscript size. It is several stories, not one coherent novel and not a narrative-quality benchmark. Unlike the parcel regression filler, this scale test does not repeat one synthetic paragraph.

On the collection, clearing process chunk/term caches before empty-disk and disk-warm runs, then measuring process-warm:

| Total context allowance | Empty-disk seconds | Disk-warm seconds | Process-warm seconds | Snapshot bytes | Recall archive bytes |
|---|---:|---:|---:|---:|---:|
| 4,096 | 0.235 | 0.174 | 0.047 | 670,322 | 660,337 |
| 8,192 | 0.222 | 0.172 | 0.049 | 684,168 | 660,337 |

Both packets fit their estimated allowances after reserving 512 output tokens and overhead. Local lexical cache files were 3,231,744 and 3,223,552 bytes. These are individual measurements in the same process, not p95 latency or process-start measurements; filesystem cache was uncontrolled. The frozen recall archive alone is about 0.66 MB per newly prepared snapshot at this size. Long-session database growth and retention/compaction remain unmeasured. Early runs with partly warm process caches are retained as diagnostics; the table uses the corrected `semantic-02` measurement method.

## Live semantic retrieval

Nomic Embed Text v1.5 was explicitly loaded locally. The first diagnostic run used plain input. Its [model instructions](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) call for different document and query prefixes for retrieval, so a profile setting now selects `plain` or `nomic-search-v1`. Plain remains the default and preserves the previous embedding identity byte-for-byte. Nomic uses `search_document: ` and `search_query: `; its format has a separate cache identity. The full 2,400-character source chunk survives the added prefix. Saving/reopening this setting was verified in the rendered app.

The prefix-correct run used the production embedding transport, normalization, independent ranking, reciprocal-rank fusion and budgeted packet construction. The query itself was fixed from the corpus probe; no query-planning or relationship-annotation call was involved. All 32 searches completed with 768-dimensional vectors.

| Prefix-correct condition | Required groups present | Complete answerable queries |
|---|---:|---:|
| Lexical candidates, up to eight | 23/34 | 14/24 |
| Semantic candidates, up to eight | 28/34 | 19/24 |
| Fused candidates, up to eight | 28/34 | 18/24 |
| Final lexical packet | 20/34 | 13/24 |
| Final fused packet | 22/34 | 14/24 |

The initial unprefixed diagnostic had 25/34 groups and 16/24 complete queries in its fused final packet, despite the same 28/34 aggregate candidate coverage. It is retained as a regression signal; we do not select the unprefixed result to claim the corrected system performs better. Ranking order and context packing need investigation. These numbers measure evidence coverage, not generated answers or manuscript continuity.

The initial run made **43 embedding calls** totaling **16.423 seconds** of sequential measured call time. The prefix-correct run made **43 corpus calls plus 19 collection-warming calls**, totaling **29.637 seconds**. Provider usage fields returned zero; actual embedding token consumption is unavailable, not proven zero.

For the 263-chunk collection, four bounded preparations each added 64 chunks and retained lexical fallback. The fifth added seven chunks and completed semantic search; the sixth reused all 263 vectors. Calls by preparation were `4, 4, 4, 4, 2, 1`, within the existing limits. The warm query took 0.406 seconds; the vector-cache file was 4,509,696 bytes. This is an explicit evaluation loop, not newly introduced automatic background work.

## Verification and artifact inventory

- 44 focused backend tests passed for semantic recall, format identity/transport, profiles, frozen trials and writer recall; another 20 provider/archive tests passed. Two existing dependency deprecation warnings were reported. These are affected checks, not a new full-suite claim.
- Ruff, ESLint, TypeScript and production build passed. Desktop 1440×1000 and mobile 390×844 browser checks saved and reopened the format setting, measured zero horizontal overflow, and recorded zero console warnings/errors or page errors. Both screenshots were inspected. The Browser plugin was unavailable; bundled Playwright used a disposable database/server. An initial mobile test had the wrong close-button selector; the corrected run passed.
- Personal profiles, manuscripts and accepted state were not edited. The checker and new guidance do not run in production. Saved writer prompt bytes, retries and acceptance behavior are unchanged by this pass. Both plain and Nomic semantic receipts were tested through archive restore/retry.
- Only the Qwen and Nomic instances loaded for this work were unloaded afterward. The user's original Ateron instance and its load configuration were verified unchanged. The disposable UI server was stopped.

Artifacts are under `C:/Users/Jim/.codex/visualizations/2026/09/19/01a0b7b5-8808-74e3-b54e-6b62ea00d044/`:

- Frozen `narrative-reliability-fixture-01`, `narrative-fresh-fixture-01`, `narrative-check-fixture-01`, `manuscript-memory-fixture-01`: manifests and SHA-256 files.
- Writing journals: `narrative-reliability-live-01`, `narrative-fresh-live-01`, `narrative-reliability-qwen-01`, `narrative-fresh-qwen-01`.
- Checking: `narrative-check-live-01`, including raw output and separate normalized replay.
- Retrieval: `manuscript-memory-local-01`, `manuscript-memory-local-02`, `manuscript-memory-semantic-01`, `manuscript-memory-semantic-02`.
- `narrative-profile-qa.json`, both `narrative-format-*.png` screenshots, model-load receipts, and `narrative-model-cleanup-01.json`.

Total new inference in this pass: **148 text-generation calls and 105 embedding calls = 253 calls**. Two model-load operations are separate from inference. No repair calls, OpenRouter calls, publication, or paid downloads were performed.

Reproduction entry points are `python -m scripts.narrative_reliability`, `scripts.narrative_fresh_cases`, `scripts.narrative_draft_check`, and `scripts.manuscript_memory_evaluation`. Use `--help` for frozen/live modes; live runs require an explicit flag and selected model, and output directories must be new. Fixture hashes are checked before execution. These commands use local artifacts, not a private manuscript.

## Remaining goal work

1. Investigate why relevant semantic candidates disappear during final packing, retaining budgets and frozen retry behavior. Evaluate any change on unchanged corpus labels and previous regressions.
2. Test an explicit, source-grounded separation of events, attributed testimony and character knowledge before drafting. Its interpretation must remain tentative; compare it against the existing writer without treating inferred state as canon. The present generic guidance/checker are insufficient.
3. Exercise ordinary writing repeatedly along a coherent manuscript, including evolving knowledge, branches and accepted revisions. Report interventions, drift, latency and database growth. Current whole-work retrieval and short continuation probes do not establish that result.

The goal remains active. This pass establishes a stronger baseline and rejects insufficient interventions; it does not establish dependable long-form continuity.
