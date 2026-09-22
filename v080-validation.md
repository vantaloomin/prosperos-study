# v0.8.0 implementation validation

Validation date: 2026-09-20. Branch: `codex/v0.8.0-personal-writing`, based on local v0.7.5 commit `515837613b67ec61087a771b9e6cb52e2f7de740`. Application metadata is 0.8.0; private archive format is 51. The verification environment uses Windows/PowerShell, Python 3.12.9, Node 22.14.0 and npm 10.9.2. This is an implementation record, not a publication record. No commit, push or tag is part of this work.

All four original author workflows and their required verification gates are complete. That full pipeline exited successfully, and all 1,082 frozen source/test/build files retained identical hashes during the run. The later Skip setup addition has its own dated verification below; the original full-suite results are historical. Browser/platform and model-quality limits are recorded below; publication remains separate.

## Release preparation — 2026-09-21

Publication was authorized separately after implementation. The release uses the annotated `v0.8.0` tag and the [GitHub release](https://github.com/vantaloomin/prosperos-study/releases/tag/v0.8.0), with a source ZIP, per-file manifest and SHA-256 checksums. The README now links to that version's download and installation/update instructions. All application version declarations agree on 0.8.0; the private archive format remains 51.

The release source was compared with the successful full-suite snapshot: 1,076 of its 1,082 files remain identical; the six differences and one added source file are the separately verified Skip setup addition described below. No application, test or build source changed during release preparation. Existing results therefore remain the verification basis; no new full-suite result is claimed. The release commit excludes the four unrelated historical-document modifications already present in the workspace.

The attached `source-manifest-v0.8.0.json` records the release commit, Git tree and file hashes. `SHA256SUMS.txt` covers that manifest and `prosperos-study-v0.8.0-source.zip`. Both downloads are built from the committed tree, rather than including local databases, dependencies or generated test artifacts.

## Skip setup addition — 2026-09-21

The [separate goal](v080-skip-setup-goal.md) adds direct Story creation from any unfinished wizard step, retained choices and pinned Library versions, an Untitled Story fallback and one-time composer focus. It reuses the existing atomic API and saved request rather than changing backend or archive contracts. The README, changelog and release notes describe the shortcut.

| Check | Measured result |
| --- | --- |
| UI-model suite | **113 passed**, including three added shortcut/default/reference/recovery cases; `npm.cmd run test:ui-models`. |
| Existing onboarding backend tests | **7 passed**, two existing test-client deprecation warnings, 3.48 seconds; `.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=<isolated-artifact-directory> tests/test_onboarding.py`. |
| Static and build | `npm.cmd run lint` and `npm.cmd run build` passed, including TypeScript; final Vite build 6.71 seconds. |
| Browser | **24 checks passed** in Chromium 151.0.7922.34 via Playwright 1.62.1, using a disposable database at `http://127.0.0.1:18786`, reduced motion, 1440×1000 and 390×844 viewports. Browser plugin not available. |
| Interactions and recovery | New Story → Skip setup → focused composer; keyboard activation, model-free manual writing, later Story editing, entered preferences and old Character edition, invalid greeting preservation, guided/back/close/reopen paths, duplicate activation and lost-response/reload recovery all passed. Explicit retry reused the exact saved payload and original writer despite a changed workspace default. |
| Rendering and console | Page identity, meaningful rendering, no error overlay, inspected desktop/narrow screenshots and no unexpected console/page/HTTP errors or warnings. One deliberately injected 503 exercised save recovery. The initial narrow screenshot exposed a generic footer rule hiding the helper; scoped CSS corrected it and the final run verified it visible. |
| Automatic work | Six disposable Stories; **zero provider calls**, generations, scene runs, review runs, chance opportunities, Companion turns, recipe runs or style-analysis jobs. |

Artifacts are outside the repository at `C:\Users\Jim\.codex\visualizations\2026\09\20\01a0bc1f-bec5-7371-bb67-cf3b48b43bda`: `skip-setup-models-02.log`, `skip-setup-backend-01.log`, `skip-setup-lint-02.log`, `skip-setup-build-03.log`, `skip-setup-browser-04.log`, `skip-setup-browser-result.json`, and the three `skip-setup-*.png` screenshots. Earlier browser logs retain test-harness selector/route failures; the final scenario passed end to end.

The full 1,756-test backend suite was not rerun for this frontend addition. Browser checks do not establish native mobile keyboard behavior, other browser engines or live model quality. No commit, push, tag or publication was performed.

## Final verification

| Check | Measured result and evidence |
| --- | --- |
| First full backend run | 1,733 passed, 10 failed, two upstream test-client deprecation warnings, 1,362.26 seconds. `test-results/v080-final-checks-01.log`. The pipeline stopped before subsequent gates. This run preceded the final structured-output fix. |
| Archive follow-up | 119 passed, two warnings, 138.44 seconds. `test-results/v080-final-fixes-01.log`. Includes every failed area, Companion edit restoration, the combined scenario and structured-output regressions. |
| Final backend suite | **1,756 passed**, two upstream test-client deprecation warnings, **1,313.29 seconds**. `test-results/v080-final-checks-02.log`. |
| Final frontend and static checks | **110 UI-model tests passed**; Ruff, ESLint, TypeScript and production build passed through `check.ps1`, exit 0. Vite completed in 4.45 seconds. The Node test command emits its existing experimental type-stripping notices. Same final pipeline log. |
| Source snapshot | All **1,082 files unchanged** before/after the final run. `test-results/v080-final-source-before-02.json` and `v080-final-source-after-02.json` both have SHA-256 `c4cc9578c89645996225c51876b169c43f373c54c737852e1c348f2ce362f11c`. |
| Whitespace | Tracked implementation changes and 200 new files passed; the four untouched historical documents are excluded and separately hash-verified. `test-results/v080-final-whitespace-01.json`; final documentation edits are checked separately in `v080-final-document-checks-01.json`. |
| Combined workflow | Passed; `tests/test_v080_integration.py` and `test-results/v080-integrated-03.log`. Repeated successfully in the focused follow-up. |
| Final release browser scenario | Nine checks passed, zero unexpected console/page/HTTP errors. `test-results/v080-release-browser-03.log`. |
| Real model evaluation | 15 calls on one already loaded local model; successful final examples and observed limitations are recorded in [the output evaluation](v080-output-evaluation.md). |

The full run found a shared mapping error: adding Companion `origin_id` to the global archive-reference set also remapped continuity origins. Those continuity values define permanent fact IDs used by later updates and frozen requests. Mapping is now specific to `side_edit_results`, whose origin is a live foreign key; continuity origins remain unchanged. Existing regression checks prove that updated facts, participant withdrawals, author plan edits and repeated restoration retain their identities and meanings. The other two failures were format-48 fixtures retaining newer empty recipe groups; those fixtures now reconstruct the actual old shape. Production migration validation remains strict.

## Combined acceptance

The disposable scenario creates a style and a typed draft/readers/revision recipe, exports their portable bundle with selected examples, and imports it into a clean workspace after explicitly mapping its missing model. It restores the genuine published v0.7.0 manuscript fixture, verifies its SHA-256 and original provider inputs, and pins the imported style in two Stories.

A saved recipe retains its original style and recipe editions while new editions are published and only the second Story adopts the new style. Four controlled calls complete drafting, two independent reader jobs and revision. Applying the selected accepted-passage proposal preserves the original telling and later prose. Comparison identifies the change; one telling is favorited, the original archived, and search finds it only with the requested archived-source option.

The Companion receives the exact revised passage, produces one styled proposal, and supports Apply followed by Undo. The original manuscript document, preview and prepared DOCX bytes remain unchanged. Recreating the application against the same database preserves the records. A format-51 workspace export/restore retains exact recipe and Companion input strings, outputs, source comparisons, favorites, archives and the original Book prose. Restart and restoration add **zero provider calls** to the four recipe calls and one Companion call.

The committed genuine fixture is `tests/fixtures/v070-manuscript-archive.json.gz`; decompressed SHA-256 is `7c8c54e66ae1844524fba04e06539661a09a849f7da4d0915db803b6821be5d0`. Existing manuscript checks also inspect DOCX/EPUB package structure, literal content, export snapshots, source validation and restored ordering/bookmarks. A generated export passing those checks is not evidence of successful reading on every ebook device.

The release browser scenario opens the archived original, reads its three original manuscript passages, inspects the imported recipe's frozen history, checks new archive counts, creates/restores a workspace archive in the browser, and opens the restored manuscript. Desktop and narrow screenshots were visually inspected. Its guard provider recorded no calls.

## Requirement audit

The rows follow the order of requirements in [the goal](v080-implementation-goal.md). Each row points to implemented behavior and its most relevant tests or recorded browser slice; overlapping runs are not added into a unique-test total. Feature-specific source lives in `server/writing`, `server/branch_tools`, `server/text_edits`, the Companion modules under `server`, and their corresponding `src/features` interfaces. Archive validation and bindings live under `server/archives`.

### Styles

| Requirement | Implementation and evidence |
| --- | --- |
| Versioned Library CRUD, duplicate/archive and explicit adoption | Writing-resource Library and Story pins; `test_writing_resources.py`; first and second browser slices. |
| Optional prose/viewpoint/tense/dialogue/rhythm/description/habits/examples | Style editor and validated optional fields; no model required for editing; resource and sample-analysis tests. |
| Explicit selected-sample analysis with editable suggestions | Selected evidence, field-level copying/conflicts, separate publication, saved attempts; `test_style_analysis.py`, `styleAnalysis.test.mjs`; fifteenth slice. |
| Request → recipe → Story precedence, explicit None and effective display | Shared resolution and request controls; resource, knowledge, scene-writing, recipe-planning and Companion-preview tests. |
| Prose/revision applicability, no factual styling | Scene/prose/Companion composition and preserved historical assessment inputs; `test_scene_writing.py`, `test_writing_tasks.py`, `test_side_edits.py`. |
| Examples separated from facts and authority | Required source/agency/structured-output boundaries and budget refusal; writing-knowledge, recipe-planning, Companion and structured-output tests. |
| Frozen editions/examples/composition/budget and original retries | Immutable snapshots, version bindings and strict archives; resource, recipe-archive, writing-task and Companion tests. |
| Reviewable selected-text style revision | Companion Apply style and recipe proposals use shared before/after, conflict, Apply and Undo; thirteenth/nineteenth browser slices and combined acceptance. |

### Recipes

| Requirement | Implementation and evidence |
| --- | --- |
| Versioned instruction/task/model/style/lens/chance bundles | Resource schema reuses existing roles, readers, routing and mechanics; resource/planning/run tests. |
| Quiet scene, tension revision and dialogue starters | Editable starter purposes and tasks; resource tests and sixteenth browser slice. |
| Basic CRUD without prompt JSON, advanced secondary controls | Library recipe editor, step ordering and retained advanced settings; sixteenth slice. |
| Typed variables, examples/defaults/requirements/literal braces | Validated literal substitution and input controls; resources, bundles and planning tests; sixteenth/nineteenth slices. |
| Complete and per-specialist preview, scope/budgets/unknown costs | Recipe planner and exact per-stage preview; `test_recipe_planning.py`; nineteenth slice. Dependent inputs remain explicitly unknown until prepared. |
| Workspace ceiling and run/recipe/Story inheritance, no work on browse/import | Planning, runtime switch checks and read-only preview; recipe/resource/bundle tests and browser request counters. |
| Portable schema, explicit samples and reference mapping | Bundle preview/import/export with local model/style/table mappings; `test_writing_bundles.py`; third slice and combined acceptance. |
| Unsupported settings visible and inert; whole configuration validation | Retained extras, redacted private connection data, strict compatibility preview; bundle/resource tests and third/sixteenth slices. |
| Frozen dependencies and historical retries | Saved plans, jobs, attempts, exact request strings and remapped live bindings; recipe-run/archive tests; nineteenth restart check and combined acceptance. |

### Branches

| Requirement | Implementation and evidence |
| --- | --- |
| Ancestry-aware side-by-side added/removed/changed passages | Saved comparison snapshots, text differences and omission handling; `test_branch_tools.py`; fourth slice. |
| Navigate/open either side and send labeled selection/comparison | Comparison UI and exact-source Companion pin; branch-tools/side-target tests; fourth/twelfth slices. |
| Reversible favorites/archive with preserved references | Optimistic curation separate from narrative revision; branch tests, fourth slice and combined acceptance. |
| Current/explicit archived selection remains usable | Shared branch selection and visible archive status; fourth/eleventh slices and release browser check. |
| Cross-branch search, filters, grouped source editions and exact navigation | Literal search and distinct changed/omitted versions; branch tests and fourth slice. |
| Browsing does not expand writer/character memory permission | Separate saved discussion sources; branch isolation and Companion source tests. |
| Restart/archive preservation | Comparison identity binding, curation restoration and no narrative replay; branch tests, fourth slice and combined acceptance. |

### Companion Pop Out and conversations

| Requirement | Implementation and evidence |
| --- | --- |
| Genuine same-origin window and return; retain other layouts | Separate route/window, docked/floating/full modes; eleventh browser slice. |
| Shared conversation/model/pins/proposals/status, protected unsent text | Saved drafts, version checks, shared receipt state and conflict review; side-draft/organization tests and eleventh–thirteenth slices. |
| No duplicate model calls/application or automatic resend | Browser locks, persisted operations and idempotent backend receipts; UI-model and backend tests; simultaneous-send/apply and lost-response browser checks. |
| Popup block, parent closure, disconnect and unavailable-target recovery | Explicit fallback/reconnect controls, independent child operation; eleventh resilience and thirteenth browser slices. |
| Keyboard/focus/title/narrow presentation | Focus restoration, accessible controls and synchronized titles; eleventh–thirteenth slices at three window sizes. Physical multi-monitor placement is unverified. |
| Rename/search/archive/reopen conversations | Versioned conversation organization retaining source links/history; `test_side_organization.py`; fifth and thirteenth slices. |
| Per-conversation unsent drafts, visible scope and stable reading | Persisted drafts/recovery plus existing reading-position model; `test_side_drafts.py`, `draftState.test.mjs`, `sideRecovery.test.mjs`, `readingPosition.test.mjs`; browser recovery slices. |
| Effective model/pin/style/recipe/task and secondary receipts | Connection/context/work cards, preview and request details; twelfth/thirteenth slices. |
| Only selected content transferred to writing | Exact-range handoff to the unsent composer, no automatic narrative acceptance; side-target and selected-content browser checks. |

### Scoped text work

| Requirement | Implementation and evidence |
| --- | --- |
| Selection from prose/composer/editors/comparisons with stable card | Unicode-aware ranges, frozen target identities and visible pins; `test_side_targets.py`; twelfth slice. |
| Follow/pin passage, scene, old revision or comparison without retargeting work | Saved context versions and immutable operation snapshots; side-target/preview tests and twelfth resilience checks. |
| Discuss/rewrite/expand/shorten/tone/style/continuity/compare actions | Task controls, applicability and fixed output contracts; `test_side_preview.py`, `test_side_edits.py`; thirteenth slice. |
| Add/insert before/after/replace/update with complete provenance | Shared typed action, target/selection/version/proposal/receipt schema; `test_text_edits.py`, `test_text_documents.py`. |
| Unsent composer and author notes | Versioned working documents and synchronized editors; text-document and side-draft tests. |
| Unaccepted prose drafts | Candidate and scene wording adapters preserve original model output and acceptance state; `test_candidate_text_edits.py`, `test_scene_text_edits.py`. |
| Accepted passages | Immutable revised path with preserved later prose and original Book references; text-edit, Companion and combined tests. |
| Story brief and scene goals | Bounded document/version adapters; text-document and scene-text tests. |
| Character and Canon fields | Existing versioned publication, external Canon-file conflict checks and unchanged Story pins; `test_text_edit_versions.py`. |
| Style guidance, recipe instructions and scoped prompts | Validated versioned fields, preserved samples/settings, Story/workspace scope; text-edit-version and recipe-archive tests. |
| Suggest versus explicitly authorized apply | Backend-recorded authority and exact target; default editable proposal, explicit one-change application; Companion tests and thirteenth slice. |
| New wording stays a proposal until application/acceptance | Draft/insertion actions share existing acceptance contracts; text-edit and Companion tests. |
| Accepted revisions preserve source/suffix/derived-memory rules and Books | Existing fork/revision rules, no replay or Book repointing; accepted-passage tests and combined acceptance. |
| Library/prompt publication and adoption remain separate | Target-specific versions/scopes, independent Story pins and safe restored workspace targets; text-edit-version tests. |
| Exact application checks and explicit conflict/rebase | Optimistic target identity/version/text checks and reviewable rebase; text-edit tests and thirteenth/nineteenth race checks. |
| Durable result and Undo preserving later work | Saved receipts and inverse-proposal conflicts; text-edit/version tests and browser Apply/Undo checks. |
| Backend authority cannot be widened by model/import/source/window | Strict target/action schemas, fixed output parsing, source validation and archive provenance; text-edit/Companion/recipe/structured-output tests. |
| No autonomous progression, settings, memory changes or cross-branch merging | Text-only adapters and role boundaries; task-applicability and denied-target tests. Optional recipe chance is draft-local and explicitly chosen. |
| Cancellation/staleness/retry/races/restart cannot double-apply or accept partial output | Durable operation/attempt receipts and complete-output checks; text-edit, Companion and recipe-run tests; restart/race browser slices. |

## Browser and platform scope

The Browser plugin was unavailable, so rendered checks used bundled Playwright/Chromium on Windows against production builds and disposable local databases. Screenshots at **1440 × 1000**, **390 × 844**, and the Companion window's **680 × 850** were visually inspected. Tests used reduced motion and exercised keyboard navigation/focus. The implementation goal records the individual checks, deliberate failures and harness corrections for each slice; they are not represented as a single rerun of every browser scenario on the final day.

Recent completed groups include 20 main recipe checks, 10 recipe resilience checks, eight recipe restart/accepted-passage checks, and nine release integration checks. The earlier Pop Out groups cover blocked windows, a real child window, closed parent, offline reload/recovery, conflicting drafts, native child closure, keyboard reopening and no resend after server restart. Deliberate connection failures, conflicts and a simulated lost response were expected; the corresponding final harnesses reported no unexpected errors.

Browser artifacts are retained under `C:\Users\Jim\.codex\visualizations\2026\09\20\01a0bc1f-bec5-7371-bb67-cf3b48b43bda`, using the prefixes recorded per slice. The final release artifacts use `v080-release-`; their QA server was stopped after verification. Real server restart tests use subprocess termination/restart, not merely page reload. The single combined Python scenario additionally recreates the application lifetime against the same database.

Native macOS installation/Keychain/browser opening, moving a physical window between monitors, exact OS window geometry, dedicated ebook readers, and this release's behavior across all cloud providers remain unverified. Popup permission and placement depend on the browser. These are stated platform limits, not inferred successes.

## Compatibility, documentation and preserved work

The README now documents styles, recipes, branch tools, scoped Companion authority, Pop Out, recovery and format-51 compatibility. Release notes and all five package/lockfile/Python/API version values agree on 0.8.0. The final documentation audit resolved 35 local links without missing destinations and verified the explicitly named tests and logs (`test-results/v080-final-document-checks-01.json`, `v080-document-evidence-01.json`). Earlier requests retain their exact historical instructions/content; current archives require the new application, and a pre-update backup is needed for downgrade. Portable bundles are distinct from private workspace archives. Private Companion inclusion remains explicit, with required edit provenance retained even when private discussion is omitted.

The inherited v0.7.5 documentation is retained. README and CHANGELOG were deliberately updated only during release preparation. The entire old changelog section and README's historical infographic links match the saved baseline. The two infographic prompt documents, `releases/v0.7.5.md`, and `v075-development-validation.md` retain their original SHA-256 hashes (`test-results/v080-final-preservation-01.json`). Final whitespace, source equality, documentation links and goal-checklist checks are recorded in `test-results/v080-final-document-checks-01.json`.

Automatic backups, cross-branch passage splicing, packaged installers, research/MCP collections, voice, image generation and simulated-character Companion / Date Mode remain outside this goal. Ordinary generated text and reader reports require author judgment; the live evaluation documents actual additions and missed instructions.
