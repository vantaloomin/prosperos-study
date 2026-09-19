# v0.7.5: prepare during reading, prioritize the next turn

Implement reusable deterministic preparation and optional prose cleanup outside the
foreground writing turn. A new writing request takes priority over optional work.
Accepted story text, branch scope, plans, and author choices remain authoritative.

## Delivery contract

- Record context preparation, provider queue wait, first text, generation, draft
  readiness, and cleanup timings separately. Report observed values, not polling
  time or estimates presented as measurements.
- Route inference through one shared scheduler. Writing and required assessment
  outrank requested helpers, which outrank automatic cleanup and maintenance.
  Constrained local services share one inference resource by default, including
  profiles using different loopback addresses. Independent resources may overlap.
- Incrementally warm existing content-addressed chunk and lexical caches in a
  bounded background worker. Coalesce work and yield to foreground preparation.
  Cache misses use the ordinary deterministic path; cached data never decides
  source eligibility or changes memory, plans, or accepted prose.
- A completed draft can be read and kept while cleanup runs. Original wording
  remains selected until the author chooses the cleaned version. Acceptance
  freezes that choice and prevents late publication from altering it.
- Preserve the existing option to finish cleanup before making a draft ready.
  Reading-time cleanup is optional, bounded to one pass, and only admitted on a
  connection with verified request cancellation and completion acknowledgement.
  Unsupported or unverified connections explain the limitation and preserve the
  usable original; they must not silently queue blocking optional inference.
- New foreground work interrupts admitted optional inference. Do not release an
  inference slot merely because a client coroutine or HTTP stream was cancelled.
  Failures and restart preserve originals; no automatic model retries.

## Implementation and verification

1. Add timings and scheduler admission/priority tests, including cancellation,
   failures, shared local resources, and independent resources.
2. Add bounded deterministic preparation; verify cache reuse, edits/forks,
   coalescing, shutdown, and unchanged retrieval results.
3. Split draft and cleanup lifecycles; verify keep/continue during cleanup,
   author selection, settings changes, stale results, and archive/restart behavior.
4. Verify the cancellation protocol with an owned request and acknowledged stop;
   gate reading-time inference on the resulting connection-specific evidence.
5. Exercise the rendered controls with controlled providers, run affected backend
   and frontend checks, and document observations and live-runtime limitations.

No extra agents, silent external routing, automatic acceptance, release, or publish
is part of this goal. Live model quality and latency claims require measured runs.

## Progress

- Goal complete under the corrected **v0.7.5** release name; no
  release or publication has been made.
- Shared scheduling, provider timings, bounded deterministic warming, independent
  draft/cleanup lifecycles, and explicit LM Studio verification are implemented.
  A cancelled queue entry cannot be admitted; repeated cancellation cannot release
  an owned background lease before terminal acknowledgement.
- Eight controlled-provider browser scenarios passed in Chrome: unverified skip,
  saved-profile verification, immediate Keep and Continue availability, typing
  interruption, toggle-off persistence, completion without a wording swap,
  reload without resending, and acceptance of the explicitly selected wording.
  Timing details, comparisons, desktop/narrow layouts, reduced motion, and 200%
  interface sizing were exercised. No console/runtime errors or measured
  horizontal overflow occurred. Screenshots were inspected. Bundled Playwright
  was used because the Browser plugin was unavailable.
- The existing loaded LM Studio model
  `ateron_gemma-4-novelist-eclipse-31b` passed actual cancellation and foreground
  handoff checks using synthetic prompts on 2026-09-19. The stop probe returned
  `userStopped` after 0.0031s; its follow-up completed in 0.5891s. In a separate
  shared-scheduler sequence, writing was admitted 0.0088s after being requested,
  strictly after background termination; visible text arrived after 1.3225s.
  All scheduler slots were released. No model or server configuration was changed.
- Final validation: **89 affected backend tests** passed after the cancellation
  and queue hardening, followed by **29 context-contract, recovery, and archive
  checks**. The initial full backend run finished with 1,159 passes and one stale
  legacy-receipt fixture failure: the fixture derived a historical request from
  today's model and accidentally included a newly added null field. Its request
  shape is now frozen explicitly, and its whole test file passed in the 29-test
  follow-up. The full suite was not repeated after this fixture-only correction.
  Ruff, ESLint, 94 UI-model tests, TypeScript, the production build, and
  `git diff --check` also passed. Two dependency deprecation warnings remain.

## Boundaries and evidence

Reading-time inference currently requires an LM Studio native local HTTP profile,
no API authentication, model-default reasoning, and a successful explicit check
for that configuration within the current app session (expires after 30 minutes).
Unsupported or unverified profiles skip optional background inference; cleanup
before ready and requested model helpers remain available. An unacknowledged stop
blocks the resource until the author restarts the server and resets the check.

Cache warming handles at most 64 pending nodes of at most 64,000 characters each,
uses the existing bounded disk index, and checks interruption between chunks.
Cold or evicted entries use ordinary deterministic retrieval. It does not
speculate about the author's next request, change source eligibility, or run
agents. Cleanup still makes at most one call and never accepts itself.

The live timings are observations from short synthetic requests, not a prose
quality or long-context speedup benchmark. They confirm termination of the app's
owned request, not GPU idleness across other clients. Full pacing analysis and
homeostatic retrieval remain outside this delivery.

Disposable browser fixtures, screenshots, detailed test logs, and live timing
receipts are retained in the task's `reading-time-qa` artifact directory. Personal
story data was not used for verification.
