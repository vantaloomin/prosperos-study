# Narrative reliability: packing and manuscript follow-up

2026-09-19. Continues [the active goal](narrative-reliability-goal.md) and [the first evaluation](narrative-reliability-evaluation.md). Existing raw artifacts remain unchanged.

## Production fix: keep query matches that are already present

The packing trace exposed an eviction error. A query hit could be recorded as `already supplied`, then be removed when adding another hit or reserving relationship notes. Only newly inserted hits and relationship members were protected. The final receipt could therefore describe a useful match as supplied when the final writer input no longer contained it.

New **recall version 5** protects the bounded query matches in both exact excerpts and whole history nodes before making room. It keeps the existing eight-read limit, additional-evidence allowance, overall context allowance, protected required material and source ordering. It does not add neighboring passages, new inference, or inferred story facts. An addition that cannot fit leaves the current packet intact.

Requests frozen at versions 1–4 retain the previous algorithm. Archive format **35** supports the new version; upgrading a version-34 archive does not rewrite its saved recall version, source packet or prompt. Fourteen historical version-4 receipts from the earlier live databases were replayed read-only: their packing results and exact final writer bytes still matched. New tests also cover generation, migration and restoration of a pending version-4 request.

### Frozen-corpus replay

The same 32 queries, 34 required evidence groups, original input packets and previously recorded live semantic rankings were used. There were no new embedding calls, label edits, or budget increases. All 128 packet constructions fit their allowances, and each old-version result matched the earlier recorded metrics.

| Final packet | Required groups, v4 → v5 | Complete answerable queries, v4 → v5 |
|---|---:|---:|
| Lexical | 20/34 → **27/34** | 13/24 → **17/24** |
| Lexical + semantic fusion | 22/34 → **28/34** | 14/24 → **18/24** |

No probe lost required-group coverage in either comparison. The eight unknown-answer queries still retrieved text; retrieving text is not proof that they are answerable. This is a retrieval improvement, not an automatic prose-accuracy score. Some ranked evidence still cannot fit the bounded additional-evidence allowance.

The seven controlled relationship cases retained **19/19 linked required passages**, including the earlier fork and excluded handoff. These fixtures use controlled model responses and establish scope/packing behavior, not live narrative interpretation.

## Source-quoted reading notes

An offline experiment added one preparatory call that could return up to three short distinctions about events, testimony, current state or knowledge. Notes had to quote an available source exactly and fit inside the unchanged 4,608-context/512-output writer allowance. Both paired writers received the same original source bytes; only the candidate received the tentative notes and a warning to verify them. Notes never became accepted memory.

Eleven cases each received one reading pass and two baseline/candidate pairs in opposite orders: **55 calls** (11 reading, 44 writing). All notes passed reference and budget admission. Ateron reported **107,267 input tokens**, **9,949 output tokens**, and **286.736 seconds** of run wall time. Reading used temperature zero; writing used 0.4 with thinking off. Labels were withheld. The implementation agent read all notes and drafts, nonblind.

Observed behavior:

- Both guided excluded-handoff drafts avoided the unsupported transfer that appeared in both paired baselines.
- Both guided earlier-fork drafts left the history unresolved. One baseline invented private intervening history; the other was substantially less problematic. This is a local improvement, not a four-sample accuracy estimate.
- Both guided withdrawal drafts used the accepted withdrawal. One baseline did; the other framed sending as settling the matter without acknowledging the withdrawal. As before, omission alone is not automatically a contradiction.
- **The successful-receipt case remained weak.** The reading note correctly identified delivery and Ilan's signed receipt, but the guided drafts still framed Ilan as waiting for an expected delivery or finding no evidence of completion. A correct note did not reliably govern the continuation.
- The fresh receipt, withdrawal and hidden-warehouse cases generally retained the intended knowledge boundaries. Some scenes still failed to advance a concrete next action. One registry draft said physical proof of delivery had been washed away, overstating what an illegible ledger proves.
- Quotation admission does not validate a whole claim: one note cited the promise as support for non-receipt, although the actual non-receipt evidence was elsewhere. The source packet remained available to the writer, but this illustrates why notes cannot become authoritative state.

The reading pass is **not promoted to production**. It adds cost and has not shown a dependable net prose improvement over the existing writer.

## Coherent manuscript trajectory through the real writing pipeline

The test starts with the exact first **18,365 words / 98,553 characters** of *A Doll's House*, ending before Act III, divided into **44 exact source passages**. Later published text and review labels never enter the story or requests. This is a coherent manuscript prefix beyond the available context, not repeated filler or a collection of unrelated stories. It is still shorter than a full novel, and familiarity from model training is a confound.

The real ordinary-writing API generated six continuations, then two on a fork before the fourth continuation. Each generation used live prewriting queries and the unchanged production writer prompt, at 8,192 context / 512 output tokens, temperature 0.4, thinking off. Semantic recall and model-generated relationship links were disabled to isolate ordinary lexical preparation and the new packer. The fourth main-path direction deliberately asked Nora to disclose the loan and forgery to Torvald on the page.

All eight drafts were mechanically accepted in a **disposable** story so later turns could inherit their successes and mistakes. There were zero manual prose corrections by test policy; that is not evidence that real authors need no interventions. The fork uses the third accepted continuation as its checkpoint. Original seed text and generated drafts remain in the saved database for review.

The run made **16 calls** (eight query plans, eight drafts), reporting **109,913 input tokens**, **1,860 output tokens**, and **92.471 seconds** wall time. Measured per-step pipeline time ranged from **11.083 to 11.935 seconds**. All eight preparations completed; every final input fit its allowance. A controlled rehearsal of the same lifecycle made no real provider calls.

Observed continuity:

- Nora's requested new disclosure occurred on the main path, Torvald acknowledged it, and later main-path drafts used that new knowledge.
- Neither fork request included the later main-path source nodes. Torvald did not recite the main-path confession in either fork draft. This combines source-scope checks with review of the actual outputs.
- The drafts retained the waiting letter and Christine's inability to reach Krogstad that evening, but sometimes upgraded writing a note into having left/sent it. The original wording supplies writing the note; the additional action deserves review rather than silent promotion to fact.
- A fork draft referred to “her encounter with Krogstad” while answering about the errand. That wording risks implying a completed errand meeting despite the out-of-town report. The earlier manuscript also contains a prior encounter, so it is not scored as an unambiguous contradiction without clarification.
- The final fork direction's phrase “delayed mail” was itself ambiguous: the model treated it as delayed postal delivery rather than deferred reading. That is a fixture limitation, not a clean retrieval failure.

All eight drafts were reviewed by the implementation agent. This single trajectory demonstrates useful continuity and real pipeline behavior; it does not estimate long-form reliability across models, manuscripts, or author interventions.

### Storage

Logical SQLite size grew from **1,212,416 bytes** after seeding to **2,879,488 bytes** after the trajectory and fork. Eight generation snapshots totaled **1,168,453 UTF-8 bytes**. The final story archive was **2,008,396 serialized bytes** and passed the current archive validator. No WAL bytes were present at the recorded measurements. These observations quantify this run; they are not a long-session retention or compaction benchmark.

## Verification and artifacts

### Thinking off/on comparison

The loaded Ateron instance reports `on` as its default reasoning option; the earlier evaluations explicitly requested `off`. A separate frozen comparison used the same original evidence and baseline writer prompt for four cases, two repetitions each, in opposite off/on orders. Both modes had the same 6,144-token context allowance and 1,536-token output ceiling, enlarged equally to accommodate reasoning. This is not directly comparable to the earlier 512-output experiments.

| Setting | Calls | Reported input tokens | Reported output tokens | Reasoning tokens included in output | Median call seconds |
|---|---:|---:|---:|---:|---:|
| Off | 8 | 18,586 | 1,587 | 0 | 5.717 |
| On | 8 | 18,570 | 8,453 | 6,894 | 23.154 |

All sixteen calls completed in 245.854 seconds wall time. The backend suite ran concurrently, so these are observed workstation times, not isolated inference benchmarks. Raw private reasoning was not needed for adjudication; the returned prose and usage were reviewed.

Thinking on more clearly preserved the signed receipt in the successful-sibling samples, but introduced awkward narrator commentary. It still invented dispatch in **both excluded-handoff samples**, versus one of the two off samples. Fork drafts were less assertive about hidden explanations, though one introduced a memory of possession before the meeting. Both modes generally preserved the warehouse knowledge boundary. This is a mixed result and does not justify a blanket setting change. Personal profiles and the loaded instance's settings were not changed.

The additional artifacts are `narrative-thinking-fixture-01` and `narrative-thinking-live-01`, with separate off/on journals. Reproduce with `python -m scripts.narrative_reasoning_evaluation`.

### Checks and preserved outputs

The affected packing, recall, semantic, relationship, archive/retry tests passed: **61 tests**. The full backend suite subsequently passed: **1,247 tests in 734.80 seconds**, with two dependency deprecation warnings. Command: `.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/narrative-consolidation-full-01`. Ruff and whitespace checks passed. This pass changes no frontend behavior, so prior desktop/mobile checks are not represented as new checks here.

New artifacts under the same task visualization root:

- `recall-packing-replay-01/report.json` and `historical-replay.json`: new/legacy packet results and read-only historical byte replay.
- `relationship-v5-controlled-01`: all seven controlled relationship cases.
- `narrative-reading-fixture-01` and `narrative-reading-live-01`: frozen notes experiment and every raw call.
- `manuscript-trajectory-fixture-01`, `manuscript-trajectory-controlled-01`, and `manuscript-trajectory-live-01`: original prefix, directions, review notes, disposable database, source scope, raw calls, receipts and storage measurements.

Reproduce with `python -m scripts.recall_packing_evaluation`, `scripts.narrative_reading_pass`, and `scripts.manuscript_continuation`; `--help` lists the explicit freeze/live modes. Live outputs require new directories. No personal manuscript, profile, prompt or accepted user prose was edited; nothing was published.

### First bounded-revision trial

The sixteen drafts from the earlier checker experiment were frozen again, including its three missed faults and six clean controls. Only its seven flagged drafts triggered a revision request. The model could propose up to two unique, non-overlapping edits of at most 500 characters each, targeting a flagged quotation. Originals were retained; nothing was accepted or changed in the app. Revision input was bounded at 8,192 context / 768 output tokens, temperature zero, thinking off; labels were withheld.

The **seven calls** reported **11,385 input tokens**, **557 output tokens**, and **22.562 seconds** wall time. All seven proposed changes passed mechanical admission. The nine unflagged drafts stayed byte-identical without a revision request, including the three faults the checker missed.

Review of complete revised drafts found useful local corrections: removal of the fabricated report to Ada, correction of the reversed obligation, separation of narrator knowledge from the warehouse characters, and reassignment of the delivery claim to Den. However, the parcel revision removed the box from the opening while leaving it present in the final paragraph, and replaced the false handoff with unsupported recipient knowledge. Another revision removed the specific earlier keeper sighting while retaining an unsupported habitual inference. The disputed withdrawal warning caused deletion of a legitimate memory of the earlier promise rather than a justified continuity correction.

Mechanical edit validity is therefore not whole-draft consistency. This proposal mechanism also remains experimental. Its next revision must consider dependent references throughout the draft and permit declining a faulty checker suggestion. No automatic repair or extra writing-loop call has been enabled. Artifacts: `narrative-revision-fixture-01` and `narrative-revision-live-01`; reproduction: `python -m scripts.narrative_revision_evaluation`.

This follow-up made **94 new text-generation calls**: 55 in the reading experiment, 16 in the manuscript trajectory, 16 in the thinking comparison and seven revision proposals. It made no new embedding calls. Across both consolidation passes there have been **242 text-generation and 105 embedding calls (347 total)**. Controlled rehearsals, packing replays and automated tests are excluded from those inference counts.

The goal remains active. The next bounded writer intervention must correct flagged claims consistently across the proposed draft, rather than treating isolated span edits as sufficient. It must preserve original drafts, stay within scope and budgets, and demonstrate useful corrections without introducing new unsupported history before any production integration.


## Subsequent completion audit

The [final consolidation audit](narrative-reliability-audit.md) records the next 46 live calls, whole-draft proposal findings, unseen contrasts, manuscript checker failures, and the optional author-requested revision implementation. It includes final verification and unresolved limits. Automatic checking and repair were not promoted to ordinary-writing defaults.
