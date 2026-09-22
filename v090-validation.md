# v0.9.0 implementation evidence

2026-09-22. **Implementation goal completed.** All four workstreams and their required verification gates are complete under [v090-implementation-goal.md](v090-implementation-goal.md), derived from the approved roadmap. The subsequent source release is documented in [v0.9.0 release notes](releases/v0.9.0.md). This record reports new measurements, not the previous release's counts. Checkpoints retain their historical status; the final completion record below supersedes earlier pending items.

## Checkpoint 1: automatic backups and recovery

Implemented the first workstream as a usable slice in **Settings → backups → Automatic backups**:

- Explicit off-by-default scheduling, 15-minute to 30-day intervals, retention of 1–365 scheduled copies per destination, and an optional private-sidebar inclusion setting.
- Default folder beside the workspace database or an existing absolute destination folder. A workspace-specific subdirectory separates this installation's copies from unrelated files.
- Durable settings, frozen per-run configuration, operation IDs, due times and history. The server checks approximately every 30 seconds while running. A missed schedule creates one catch-up copy. Saving settings starts a new interval; disabling stops future scheduled work.
- A separate **Back up now using saved settings** action. These on-demand copies and existing manual private archives are excluded from scheduled retention.
- Validated archive construction, exclusive temporary files, flush/readback, atomic publication, and hash verification on recovery. Retention happens after a successful scheduled copy and refuses changed/unowned paths. Failed attempts preserve older copies.
- History of the most recent 100 attempts with destination, status, size, private-content choice, availability, and failure or retention messages. **Review & recover** stages a verified local copy for the existing download and explicit **Restore as new Stories** flow.
- Restore preserves original Stories and checks duplicate restore receipts. Local scheduling settings and destination paths are excluded from archive contents; imported archives cannot activate backups.

The archive wire format remains 51 because the new database tables describe installation-local backup management, not portable story data. Existing manual archives use the same construction/validation path as before.

### Measured backend and build checks

| Check | Observed result |
| --- | --- |
| Focused backend suite below | **46 passed**, 54.75 seconds; 19 are new automatic-backup tests |
| Existing UI-model suite | **113 passed**, no failures |
| Ruff over `server tests scripts` | Passed |
| ESLint | Passed |
| TypeScript + Vite production build | Passed |
| `git diff --check` | Passed; Git emitted line-ending normalization notices |

Focused backend command:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_automatic_backups.py tests/test_archives.py tests/test_archive_recovery.py tests/test_v07_manuscript.py tests/test_v080_integration.py --tb=short --basetemp=test-results/v090-backups-04
```

Additional commands: `.venv\Scripts\python.exe -m ruff check server tests scripts`, `npm.cmd run test:ui-models`, `npm.cmd run lint`, `npm.cmd run build`, `git diff --check`.

Coverage includes disabled/default schedules; validation and stale settings; due-time/catch-up behavior; retention preserving manual and unrelated files; multiple destinations; unavailable destination recovery; an injected flush failure; tamper rejection and retention refusal; duplicate and concurrent triggers; exact frozen settings; Book arrangement and original-path recovery; fresh-workspace restore of saved requests, outputs and old Library versions; sidebar inclusion/exclusion; credential-reference exclusion; startup recovery; actual background scheduler execution without a browser; exact imported PNG/source/Markdown recovery; missing files; path escape rejection; and disabling during a running backup. Existing archive recovery cases also cover unfinished-request interruption and explicit retry.

An early concurrency test exposed a startup race: a scheduler check with no due work briefly held the execution lock and could reject a simultaneous manual request. The implementation now claims due work transactionally before serializing actual file creation/retention. The final focused suite passed after the fix. Initial test assertions using a nonexistent candidate `text` field and source route were corrected to the existing `output` and Markdown contracts.

The two reported backend warnings are existing Starlette/httpx and AnyIO deprecation warnings. No full backend release-suite run is claimed at this checkpoint.

### Browser verification

Browser plugin not available; used installed Playwright/Chromium against the production build on an isolated Windows workspace at `http://127.0.0.1:8793`. No dependencies were installed and the author's normal database was not used.

Flow: **Settings → backups → save schedule/destination → reload → create on-demand copy → review → download → deliberately restore → open recovered prose → exercise an unavailable destination**.

**18 recorded checks passed**, covering page identity, meaningful content, absence of a framework overlay, off-by-default state, keyboard toggling, saved settings/due time, reload persistence, chosen destination, recovery-preview focus, downloadable private content with no scheduling authority, a distinct restored Story, opening recovered prose, original preservation, visible failure, narrow layout, reduced motion, enlarged text, and console health. No console or page errors were recorded.

Viewports: **1440×1000** and **390×844**. The narrow view was also checked at **200% root text size**, with no horizontal page overflow. Screenshots were visually inspected. This is focused Chromium evidence, not broad accessibility or native-platform acceptance.

Local evidence lives outside the repository in:

`C:\Users\Jim\.codex\visualizations\2026\09\22\01a0c9d7-0ae0-71c3-b6a4-eefbb08bcdfb\`

- `backup-browser-check.cjs` — repeatable workflow against a fresh isolated database.
- `backup-browser-results.json` — named checks and observed identifiers.
- `backups-desktop.png`, `backups-restored-desktop.png`, `backups-mobile.png`, `backups-mobile-large-text.png` — captured UI evidence.

### Limits and remaining acceptance

- Scheduling requires a running app server. There is no OS-level wakeup, closed-app scheduler, or direct cloud-account integration.
- Backups inherit the private JSON archive's 128 MiB limit and its exclusions, including credentials and unsaved browser-only recovery text.
- The destination test used an ordinary available folder and a deliberately unavailable path. Physical drive removal, real full-disk failure, network-share behavior, power-loss durability, native macOS, and simultaneous app-server processes sharing one database were not measured. Interrupted runs remain visibly interrupted; any unreferenced partial file left by a process crash is never offered as a completed recovery copy.
- The new workspace schema was exercised through fresh initialization, restart and existing archive restore. A full release regression and dedicated retained v0.8.0 database upgrade fixture remain for the final integration gate.
- At checkpoint 1, migration, weighted decks, portable collections, and standalone HTML publishing remained unimplemented. The container slice below advances migration; its remaining acceptance stays open.
- Existing `README.md` and `ROADMAP.md` changes were preserved. No version bump, commit, tag, push or release publication was performed.

## Checkpoint 2: CHARX and BYAF containers

Implemented and browser-verified the [bounded character-container mappings](migration-compatibility.md): content detection, preserved exact ZIP downloads, inspectable converted documents, local asset previews/downloads, explicit portrait selection, inactive world-info proposals, and archive preservation of all supported embedded images. BYAF histories and generation settings stay inspectable reference material in this character flow.

Measured checks:

- **85 backend cases passed in 71.44 seconds**, including 29 new container cases: `.venv\Scripts\python.exe -m pytest -q tests/test_character_containers.py tests/test_library_imports.py tests/test_native_imports.py tests/test_artwork.py --tb=short --basetemp=test-results/v090-containers-02`.
- A subsequently added damaged-DEFLATE regression **passed separately in 0.67 seconds** (`tests/test_character_containers.py::test_damaged_deflate_is_a_reviewable_import_error`, `--basetemp=test-results/v090-container-damage`). There are now 30 container cases. Do not interpret these two runs as one 86-case run.
- Ruff, ESLint, TypeScript and Vite build passed for this slice. A downloaded upstream reference `.js` initially entered ESLint's input; it was renamed to `.txt` in ignored `tmp/`, then lint passed. No upstream executable code was added to product source.
- **17 browser checks passed**, using installed Playwright/Chromium and the production build at isolated port 8794. They cover visible format detection, preview without publication, both image previews decoded, unsupported/remote limits, byte-exact source download, chosen artwork and edited name, linked Canon without Story adoption, preserved BYAF conversation inspection, narrow layout, reduced motion, Escape focus restoration, reload persistence, no external requests and no console/framework errors.
- Screenshots were visually inspected at **1440×1000** and **390×844**. Evidence alongside checkpoint 1: `container-browser-check.cjs`, `container-browser-results.json`, `container-charx-desktop.png`, `container-byaf-mobile.png`. Fixture images are deliberate solid-color test artwork. Repeated browser runs added copies only in the isolated QA database.

The tests caught Windows ZIP-name normalization: validation now uses the original directory entry name, rejecting raw backslashes and NUL bytes before Python's normalized filename can hide them. The browser found an artwork selector whose hint polluted its accessible name; explicit label/description IDs corrected it. Initial browser assertions were also adjusted to await decoded thumbnails, Radix focus restoration and reloaded Library data, and to leave narrow-screen Story navigation before checking the desktop Library.

Source-format mappings were checked against pinned primary CHARX/BYAF specifications linked in the compatibility record. No external accounts, real user exports, live models or universal source-application equivalence were tested. Mixed migration and the other v0.9 workstreams remain open.

## Checkpoint 3: reviewed transcript migration

Implemented **Library → Migrate writing** for bounded SillyTavern JSONL, text-only role/content JSON and UTF-8 text/Markdown transcripts. The author reviews source order, speaker roles, reference-only messages and alternate replies, then explicitly imports selected messages as a new Story. Text/Markdown begins wholly unselected. Protected structured source roles cannot be accepted as narrative. Exact originals, conversion reports and recorded selections are available through **Story setup → Preserved migration sources**.

The implementation preserves all source variants while accepting only the chosen telling, disables randomness in the newly imported Story, and queues no model work. Exact-source and full-message-content duplicates are reported, default to skip, and need an explicit choice to create another Story. Same names are not identity. Transactional imports and operation receipts protect retries and rollback. Recent staged sources and browser mapping drafts can be reopened locally.

Archive format **52** adds portable transcript source records and immutable Story import receipts. Story-scoped and workspace archives include imported sources; unimported staging and browser-only edits are excluded. Validation recomputes conversion from exact bytes and checks accepted text, roles, ordering, node/source ownership and the recorded variant. Restore remaps live source, receipt and node links while preserving source bytes and original labels. A retained v51 shape upgrades with empty transcript groups; the genuine released v0.7 fixture and v0.8 cross-feature integration also pass through the new format.

### Measured checks

- **122 backend tests passed in 119.26 seconds**, including the initial 34 transcript cases and all 30 container cases, with the same two pre-existing deprecation warnings. Command:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_transcript_migration.py tests/test_archives.py tests/test_recipe_archives.py tests/test_archive_lineages.py tests/test_v080_integration.py tests/test_style_analysis.py::test_format_49_upgrades_with_only_empty_analysis_groups tests/test_scene_writing.py::test_format_48_scene_restores_unchanged_without_new_writing_fields tests/test_writing_tasks.py tests/test_character_containers.py --tb=short --basetemp=test-results/v090-transcripts-03
```

- **113 existing UI-model tests passed**, 411.964 ms. Ruff over `server tests scripts`, ESLint, TypeScript/Vite build and `git diff --check` passed. These are measured current checks, not the full release backend suite.
- Initial test setup exposed oversized pytest parameter IDs on Windows, fixed with short descriptive IDs. After the archive bump, eight legacy-fixture tests initially failed because their reconstructed old archives retained new record groups. Fixture reconstruction now removes those groups; strict production validation was preserved. The 122-case run is the post-fix result.
- Five later backend regressions were added for protected role normalization and existing-Story/fork/receipt isolation. Their follow-up result is recorded below; they are not part of the earlier 122-case count.
- The final transcript/automatic-backup follow-up **passed 58 tests in 50.18 seconds**: all 39 transcript cases plus 19 backup cases, after the protected-role refinement and format 52 integration. Command: `.venv\Scripts\python.exe -m pytest -q tests/test_transcript_migration.py tests/test_automatic_backups.py --tb=short --basetemp=test-results/v090-transcripts-backups`. This is a separate overlapping run, not 58 additional distinct tests.

### Browser evidence

**21 recorded checks passed** using installed Playwright/Chromium, production build, and an isolated database at `http://127.0.0.1:8795`. Flow: stage JSONL → inspect protected/system material → choose an alternate and narrator mapping → download exact original → explicitly import → open Story → inspect source/mapping and rejected alternate → reload → skip a duplicate → stage Markdown → explicitly map one speaker → close with Escape.

The browser confirmed no Story creation during staging, correct accepted order and provenance, literal markup in review, duplicate skipping, preserved alternatives, persistent Story prose, explicit text mapping, focus return and no external requests or console/framework errors. Viewports: **1440×1000**, **390×844**, and narrow view with computed root text size verified at **32px (200%)**, with no horizontal dialog overflow. Reduced motion was enabled. Screenshots were visually inspected.

Evidence alongside prior checkpoints: `transcript-browser-check.cjs`, `transcript-browser-results.json`, `transcript-review-desktop.png`, `transcript-review-mobile.png`, `transcript-review-large-text.png`, and `browser-original-transcript.jsonl`. Browser runs only changed their isolated QA database. The QA server was stopped afterward.

Browser findings corrected in the product: explicit accessible names for select controls, initial bulk-mapping selection of an eligible speaker, and hiding the old actionable review while a replacement file is being staged. The validation script was also corrected to await reloaded prose and the specific newly staged source instead of reading the previous preview.

### Remaining scope

This checkpoint does not complete migration. Mixed batches, character/world-info/preset deduplication, foreign preset conversion and combined multi-format acceptance remain open. Weighted decks/collections, standalone Book HTML, full release regression, final help updates and retained v0.8 database upgrade verification also remain open. No live model/provider, user export corpus, native macOS or every historical dialect compatibility is claimed.

Existing `README.md`, `ROADMAP.md`, and concurrently appearing `design/promo/` work were left untouched. No commit, release version bump, tag, push or publication was performed. The encompassing goal remains active.

## Preset groundwork checkpoint (superseded by checkpoint 4 below)

The pure converter in `server/migration/preset_conversion.py` recognizes SillyTavern text-completion shapes, chat-completion shapes and the inspected NovelAI `presetVersion: 3` parameters envelope. The pinned SillyTavern `preset-manager.js`, `openai.js`, `textgen-settings.js` and `nai-settings.js` sources were inspected at commit `06bde939fb1e9c4c8d8641d810f0a916b5bce127`. Its NovelAI adapter explicitly recognizes that v3 envelope; newer/different NovelAI preset shapes remain rejected. Official NovelAI settings documentation was used to confirm that sampling semantics are model-dependent.

This is **conversion groundwork only, not a usable preset-import feature yet**. It is not connected to staging routes, persistence, archive provenance, recipe publication, native profile review or the migration UI. Mixed-file batches have not been implemented. Those are the next required work items; none of the corresponding goal checkboxes is complete.

The converter proposes bounded sampling values without coercing/clamping unsupported ones, offers chat-prompt fragments for explicit selection, preserves foreign macros as literal text in native recipe syntax, and rejects known nonempty exported credential fields before preservation. Provider/model identity, sampler order, injection depth and foreign runtime settings are not activated. Exact original preservation and durable compatibility receipts still need integration.

Its initial **21 pure conversion tests passed in 0.18 seconds** (`tests/test_preset_conversion.py`, `--basetemp=test-results/v090-preset-conversion`), covering the three dialects, literal macros, range/type limits, credential fields, unsupported/ambiguous variants and bounds. A subsequent function extraction addresses Ruff complexity; the post-extraction result is recorded next.

Post-extraction verification: **21 passed in 0.18 seconds**, using `--basetemp=test-results/v090-preset-conversion-02`; full Ruff and whitespace checks passed. No UI or end-to-end preset-import claim is made.

## Checkpoint 4: reviewed foreign presets

The converter is now connected to durable staging, explicit recipe publication, optional local profile copies, source downloads, version-history inspection and archive format **53**. Supported dialects and exact limits are in `migration-compatibility.md`. Instruction/sampling selections begin empty; foreign macros are literal. Publication does no model work, changes no Story pins or primary writer, and copies no saved credentials. New versions require the exact target identity/current version. Exact-source and proposal-content duplicates default to skip; repeated operations reuse the original result.

The UI lives at Library → Migrate writing → Generation presets. It supports fragment selection, edited recipe text, capability-checked sampling previews with before/after values, explicit duplicate/version decisions and persisted review drafts. Recipe editors and earlier-version views expose the immutable imported source/receipt. Accepted sources and local configuration provenance survive fresh-workspace restore and re-export; staged-but-unpublished sources and browser drafts stay local.

Measured checks:

- **102 backend tests passed in 94.56 seconds**: `tests/test_preset_migration.py`, `tests/test_preset_conversion.py`, `tests/test_archives.py`, `tests/test_recipe_archives.py`, `tests/test_archive_lineages.py`, the format-49 style-analysis and format-48 scene-writing upgrade tests, and `tests/test_writing_tasks.py`; `--basetemp=test-results/v090-presets-02`. Log: `test-results/v090-presets-02.log`. The initial run used the wrong archive endpoint in the new tests; corrected tests use the established `/api/archives/imports` contract. Production archive validation was not weakened.
- After adding Story-scoped provenance and literal rendering assertions, **83 tests passed in 70.49 seconds**: all 25 preset-migration, 39 transcript and 19 automatic-backup cases; `--basetemp=test-results/v090-presets-03`, log `test-results/v090-presets-03.log`. These runs overlap and are not additive counts. Coverage includes same-name nonduplicates, stale profile/recipe updates, unsupported provider controls, atomic failures, credential rejection, exact bytes, source/configuration/receipt tampering, old format 52 and fresh restore/restart.
- **113 UI-model tests passed in 382.3832 ms**. Full Ruff, ESLint, TypeScript/production build and whitespace checks passed. Build log: `test-results/v090-presets-build.log`; UI log: `test-results/v090-presets-ui-models.log`.
- **24 browser checks passed** on a dedicated local database at port 8796 using installed Playwright Chromium: empty default selections, explicit fragment insertion and correction, literal macros/markup, capability rejection/recovery, before/after profile preview, exact download, inactive profile copy, reload retry, duplicate skip, explicit v2 update preserving v1, rejected credential source, earlier-version inspection, Escape/focus return and zero external requests. Only the two deliberately invalid HTTP requests failed; no unexpected console/page errors or framework overlay occurred.
- Browser screenshots were inspected at **1440×1000**, **390×844**, and a verified **32px root font (200%)**, with reduced motion. No horizontal dialog overflow was measured. The initial browser run exposed the textarea value entering its implicit label; the editor now uses the existing explicit `TextField` label component. A later script-only navigation assumption was corrected before the successful run.

Browser script, report and screenshots: `C:\Users\Jim\.codex\visualizations\2026\09\22\01a0c9d7-0ae0-71c3-b6a4-eefbb08bcdfb\preset-browser-check.cjs`, `preset-browser-results.json`, `preset-review-desktop.png`, `preset-review-mobile.png`, `preset-review-large-text.png`. Isolated DB: `data/v090-preset-browser.sqlite3`. No live provider output or arbitrary external export corpus was tested.

Migration remains incomplete until mixed-file batches, Library duplicate review and combined acceptance are implemented. Decks/collections, Book HTML and the full completion gate remain open. The goal stays active; unrelated README, roadmap and promotional-art work remain untouched.

## Checkpoint 5: Library duplicate review

Character and Canon import proposals now distinguish exact original-file matches from equivalent proposed content, independently for each part. Display names do not identify an update target. Prior matches default to skip; explicit copies and current-version updates remain possible. Publication rechecks duplicates inside the transaction, and the result lists skipped parts separately. Skipped Canon does not silently link a newly created character to a prior resource. Existing Story pins and published versions remain intact. The preview bounds its matching-version display to 50 per part.

Legacy import operation fingerprints remain compatible when the new optional decision field is absent. Duplicate evidence derives from existing immutable source reports and publication links, including after restoration, without another archive format change. Changed review fields now clear the compatibility acknowledgement.

Measured checks:

- **62 existing import tests passed in 47.12 seconds**: `tests/test_library_imports.py`, `tests/test_native_imports.py`, `tests/test_character_containers.py`; `--basetemp=test-results/v090-library-dedup-01`, log `test-results/v090-library-dedup-01.log`.
- **7 new duplicate tests passed in 6.96 seconds**, then **the same 7 passed in 6.72 seconds** after bounding the displayed matches: `tests/test_library_import_duplicates.py`, `--basetemp=test-results/v090-library-dedup-03`. They cover same-name nonduplicates, equivalent content with changed name/metadata, default skip, deliberate copy, retry, publication-time races, partial part matches, explicit updates/stale versions, old operation receipt replay and archive restoration. The repeated runs are not additional distinct cases.
- Full Ruff, ESLint, TypeScript/production build and whitespace checks passed; final build log `test-results/v090-library-dedup-build.log`.
- **11 browser checks passed** on isolated port 8797: visible exact/equivalent match explanations, default skip and visible result, explicit new copy, explicit target update preserving v1, acknowledgement reset after edits, desktop/narrow layout and verified 200% root text. Zero external requests or console/page errors. Desktop **1440×1000** and narrow **390×844** screenshots were inspected with reduced motion enabled.

Browser evidence is alongside the prior checkpoints: `library-dedup-browser-check.cjs`, `library-dedup-browser-results.json`, `library-dedup-desktop.png`, `library-dedup-mobile.png`. Isolated DB: `data/v090-library-dedup-browser.sqlite3`. Both preset and duplicate-review QA servers were stopped after verification.

Next required work is mixed-file staging/review with per-item durable results and retry/restart behavior, including the combined transcript/container/preset/duplicate acceptance scenario. The broader migration checkboxes remain open until this is delivered. Weighted decks/portable collections, standalone Book HTML, and the full regression/completion gate remain outstanding. No release publication has occurred.

## Checkpoint 6: mixed migration queue and combined recovery

The Library migration dialog now stages bounded mixed batches, identifies valid interpretations, isolates per-file errors, and reuses each format's detailed review. Authors can omit a file, correct mappings, choose duplicate behavior and publish items separately. Successful results and frozen interrupted choices persist across restart. Retrying after a committed import reuses its operation receipt, including native archive recovery after the staging file disappears. Completed queue receipts are immutable. The installation-local queue is outside private archives; accepted foreign sources remain archived with their published records. Exact native archive/bundle envelopes remain downloadable from the queue under the existing native import boundary, documented in `migration-compatibility.md`.

Measured checks:

- **139 backend tests passed in 103.11 seconds**: `tests/test_migration_batches.py`, `tests/test_preset_conversion.py`, `tests/test_transcript_migration.py`, `tests/test_preset_migration.py`, `tests/test_library_import_duplicates.py`, `tests/test_character_containers.py`; `--basetemp=test-results/v090-batches-03`. Log: `test-results/v090-batches-03.log`. This includes 16 batch cases and the huge-integer preset regression. Two existing test-client deprecation warnings remained.
- **115 backend tests passed in 126.10 seconds** after adding deliberate combined adoption/recovery assertions: `tests/test_migration_batches.py`, `tests/test_library_imports.py`, `tests/test_native_imports.py`, `tests/test_archives.py`, `tests/test_recipe_archives.py`, `tests/test_archive_lineages.py`, `tests/test_v080_integration.py`, `tests/test_automatic_backups.py`; `--basetemp=test-results/v090-batches-04`. Log: `test-results/v090-batches-04.log`. Runs overlap; these are not additive distinct counts. The combined test adopts imported character/Canon versions and the reviewed recipe, publishes a later recipe revision, restarts, restores into a fresh workspace, and verifies old pins, source bytes and original prose.
- A subsequent detector matrix test stages **14 character/world-info variants in one batch**: cards V1/V2/V3, Pygmalion, legacy Faraday, the five existing entry-book dialects, NovelAI versions 3–5 alongside v6, and BYAF. It verifies explicit Library reviews, same-name nonduplicates and no staging-time publication. **1 test passed in 1.94 seconds**, recorded in `test-results/v090-batches-matrix.log`.
- **113 UI-model tests passed in 377.6806 ms** (`test-results/v090-batches-ui-models.log`). Full Ruff, ESLint, TypeScript/Vite build and whitespace checks passed. Final UI build is in `test-results/v090-batches-build.log` and ESLint in `test-results/v090-batches-lint.log`.
- **24 browser checks passed** using installed Playwright Chromium and isolated port 8798: eight mixed inputs, transcript role/swipe correction and order, container artwork review, character/Canon publication, inert preset publication with an intentionally dropped successful response, default duplicate skip, individual malformed-file rejection, ambiguous text/role review, omission, native restore/bundle import, exact source download, persisted outcomes and Escape/focus return. No external requests or unexpected console/page errors occurred; the single console failure was the deliberately dropped response.
- Desktop **1440×1000**, narrow **390×844**, and verified **32px root text (200%)** screenshots were inspected with reduced motion. No horizontal dialog overflow was measured. Browser validation exposed a stale preview refresh after omission; queue actions now exclude retired review queries from their shared refresh. A repeat-run script also needed an explicit new-copy choice for the previously imported native bundle; the default application skip was correct.

Browser evidence: `C:\Users\Jim\.codex\visualizations\2026\09\22\01a0c9d7-0ae0-71c3-b6a4-eefbb08bcdfb\batch-browser-check.cjs`, `batch-browser-results.json`, `batch-review-desktop.png`, `batch-review-mobile.png`, `batch-review-large-text.png`. Isolated DB: `data/v090-batch-browser.sqlite3`. Its QA server was stopped after verification. Backend tests simulate process restart and interrupted publication; browser checks prove reload and dropped-response recovery. No live provider or arbitrary external export corpus was tested.

Backups and bounded migration now have focused acceptance evidence. Weighted decks/portable collections, standalone Book HTML and the final whole-release regression gate remain open. The encompassing goal stays active; no GitHub publication, version bump or release tag has occurred.

## Checkpoint 7: weighted inspiration decks and portable collections

The Library Inspiration tab supports immutable deck versions, stable card IDs, copies, archive/restore, seeded previews with exact odds and exclusion explanations, explicit recorded draws and paginated history. Story handoff appends a chosen card to existing unsent input and returns focus there. It neither sends the input nor enables Story RNG. Collections have bounded format-1 definitions, reviewable duplicates and exact original downloads; three editable starter collections contain five cards each. Draw and collection publication retain frozen pending operations before sending so lost responses and reloads recover the original result.

Private archive format **54** adds validated deck/version, draw and accepted pack-source/origin groups. Older formats acquire empty groups. Story archives include referenced decks; workspace archives include all decks. Card IDs, exact probabilities, outcomes, sources and historical versions survive restore. Portable collections contain selected deck versions and inert metadata, without Story/private/provider records. Limits and author instructions are in `inspiration-compatibility.md`.

Measured checks:

- **184 backend tests passed in 189.47 seconds** (`test-results/v090-inspiration-02.log`, `--basetemp=test-results/v090-inspiration-02`): the then-current 26 deck cases plus archives, recipe archives, archive lineages, v0.8 integration, backups, batches, presets, transcripts, older style/scene archive upgrades and writing tasks. This overlaps earlier checkpoint runs.
- After adding older draw-history navigation, **27 deck tests passed in 24.27 seconds** (`test-results/v090-inspiration-04.log`). The additional frozen-request acceptance case is included in the **39 tests passed in 35.18 seconds** described below: 28 deck, 5 HTML and 6 existing Book tests. One local test invocation initially hit the sandbox's default temporary-folder permissions; subsequent runs use explicit workspace `--basetemp`. New test assertions were corrected to inspect the existing JSON `snapshot.content` contract rather than invent a top-level direction field.
- **113 UI-model tests passed in 359.2546 ms** (`test-results/v090-inspiration-ui-models.log`). Ruff, ESLint and the production build passed. The final deck browser rerun used the corrected shared Library card stylesheet and waited for the actual editor before capturing its desktop screenshot.
- **32 browser checks passed** (`inspiration-browser-results.json`) on isolated port 8799: creation, weight edits and stable IDs; 25/75/0 and excluded-card odds; empty eligibility; storage-quota refusal before submission; explicit receipt/copy; version history; selected-version collection export; default duplicate skip; exact originals; deliberate copy with dropped-response/reload recovery; archive/restore; starter review; recorded draw with dropped-response/retry; unsent-input append and focus; no accepted prose, Story RNG or model work; separate fork history; narrow/enlarged layouts and Escape. Only the deliberately invalid preview and two deliberately lost responses produced request/console errors. No external requests or unexpected page/console errors occurred.
- Desktop **1440×1000**, narrow **390×844**, and verified **32px root text (200%)** screenshots were inspected with reduced motion. The deck editor had no measured horizontal overflow.

Browser evidence directory: `C:\Users\Jim\.codex\visualizations\2026\09\22\01a0c9d7-0ae0-71c3-b6a4-eefbb08bcdfb`. Files: `inspiration-browser-check.cjs`, `inspiration-browser-results.json`, `inspiration-desktop.png`, `inspiration-mobile.png`, `inspiration-large-text.png`. Isolated database: `data/v090-inspiration-browser.sqlite3`; the QA server was stopped after verification. Simulated local provider output verifies request freezing, not live prose quality.

## Checkpoint 8: standalone HTML and combined recovery

Book publishing now prepares HTML beside DOCX and EPUB from the same frozen selection, with optional contents navigation. The UTF-8 file embeds responsive/print CSS and requires no network or JavaScript. Publication rendering explicitly selects title, author, language, chapters, scene headings and prose; private workspace/source records are excluded. Paragraphs, line breaks and literal text follow the existing Book contract, including escaped raw markup. See `html-publishing.md`.

Measured checks:

- **39 backend tests passed in 35.18 seconds**: `tests/test_inspiration.py`, `tests/test_html_publication.py`, `tests/test_v07_manuscript.py`; `--basetemp=test-results/v090-html-02-tmp`, log `test-results/v090-html-02.log`. They cover selected historical tellings across branches, agreement with DOCX/EPUB prose order, Unicode and dangerous literal text, frozen downloads, restart and fresh archive restore, optional contents/scene headings, old prepared snapshots, missing publications and existing empty/invalid selection rejection. The older prepared-publication fixture uses a separate insertion; the initial attempted update correctly hit the existing immutability trigger and was fixed in the test.
- **6 tests passed in 12.13 seconds** after the print-focus adjustment: `tests/test_v090_integration.py` and the 5 HTML cases; `--basetemp=test-results/v090-integrated-01-tmp`, log `test-results/v090-integrated-01.log`. The combined scenario imports a transcript, CHARX character/Canon and inert preset; deliberately pins reviewed resources; imports a starter deck and records a draw; freezes its text in a simulated generation request; selects a Book; takes a scheduled backup to an explicit destination; changes the original workspace; and restores into a clean workspace. Exact imported/pack sources, old pins, card/outcome/eligibility, saved request/output and selected prose survive. The restored Book produces byte-identical HTML. Scheduling and the local batch queue are not activated/copied, and original later prose remains separate.
- **23 browser checks passed** (`html-browser-results.json`): saved Book reordering/metadata, all three downloads, HTML prose/order/privacy/source inspection, optional contents reset, desktop/narrow/enlarged publishing, standalone offline reading with JavaScript disabled, semantic headings, literal markup, keyboard contents navigation, narrow long-word wrapping, enlarged reading and print page-break/focus styles. There were **zero external requests, failed HTTP responses or console/page errors**. The first script run referenced the wrong existing field label; it was corrected to **Book title** before the successful checks.
- Inspected publishing and offline-reading screenshots at **1440×1000**, **390×844** and **32px root text**, with reduced motion. Generated the browser print preview, rendered its **4 Letter pages with Poppler**, and inspected every page. This caught a focused contents-target outline crossing a page boundary; print CSS now suppresses focus outlines. The final four rendered pages have readable margins, wrapped long prose, intact Unicode and clean chapter starts. No dedicated e-reader or physical printer was tested.
- **113 UI-model tests passed in 359.5701 ms** (`test-results/v090-final-ui-models.log`). Full Ruff passed; ESLint and TypeScript/Vite build passed (`test-results/v090-html-lint.log`, `test-results/v090-html-build.log`). Whitespace checks passed with existing line-ending normalization notices.

Browser evidence alongside checkpoint 7: `html-browser-check.cjs`, `html-browser-results.json`, `html-publish-*.png`, `html-reader-*.png`, `book-offline.html`, `book-no-contents.html`, comparison DOCX/EPUB downloads and `book-print-page-1.png` through `book-print-page-4.png`. These are isolated QA artifacts. Database: `data/v090-html-browser.sqlite3`, port 8800; the QA server was stopped after verification.

## Completion gate

The complete backend regression passed: **1,948 tests in 1,660.92 seconds (27 minutes 40 seconds)**, with the two existing Starlette/httpx and AnyIO deprecation warnings and no failures. Command:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=test-results/v090-full-01-tmp
```

Log: `test-results/v090-full-01.log`. This covers existing v0.8 writing/setup, styles/recipes, Companion, branches, immutable requests, Book selections, Library sources, legacy archives and the new workstreams. The final two cases added after collection are covered by the focused run below; overlapping test counts are not additive.

Archive validation now also rejects a draw whose recorded head belongs to a different telling within the same Story. It caches ancestor IDs per head and includes removal-marker boundaries; ordinary later append operations preserve the earlier draw. **30 tests passed in 42.16 seconds** after this adjustment: the now-29 deck cases plus `tests/test_v090_integration.py`, `--basetemp=test-results/v090-draw-path-01-tmp`, log `test-results/v090-draw-path-01.log`. Ruff passed. These focused cases supplement the full regression that was already running; the combined integration test and final same-Story path-tampering case were added after that run collected its tests.

The complete **113-test UI-model suite** passed in **359.5701 ms**. The final TypeScript/production build is recorded in `test-results/v090-html-build.log`; full ESLint and Ruff passes are recorded in `test-results/v090-final-lint.log` and `test-results/v090-final-ruff.log`. Tracked diff whitespace checks passed, and **91 new implementation files** were checked with **zero trailing-whitespace findings**. Browser success, validation errors, recovery, focus/keyboard, narrow/enlarged layouts, reduced motion, offline reading and print coverage are detailed per checkpoint above.

All four required workstreams and the combined recovery scenario are implemented and verified. No known defect remains that prevents a required v0.9 workflow. The compatibility documents state bounded format support and installation-local staging/publication boundaries. Native macOS, packaged installation, broad live-provider quality, demanding-branch performance, dedicated e-readers and physical printers are not claimed by these checks; the roadmap's v1.0 and optional work remains separate.

At completion of the implementation goal, unrelated README changes remained two added lines, the approved roadmap remained untouched, and promotional artwork remained outside the implementation changes. No commit, version bump, tag, push or GitHub release had been made at that checkpoint. The author subsequently authorized official release preparation and publication.

## Source release preparation

The subsequent release task updates the application, frontend package/lock and Python package versions to **0.9.0**, with matching README, changelog and release notes. The pre-existing README roadmap addition, untracked roadmap and promotional artwork remain outside the release allowlist. No new dependencies were introduced.

After the version and documentation changes, **6 focused backend tests passed in 9.32 seconds**: `tests/test_v090_integration.py` and `tests/test_html_publication.py`, with `--basetemp=test-results/v090-release-tmp`. Log: `test-results/v090-release-backend.log`. The two existing deprecation warnings remain. Ruff, ESLint and a fresh TypeScript/production build passed; the latter logs are `test-results/v090-release-lint.log` and `test-results/v090-release-build.log`. The full backend suite was not rerun for release metadata/documentation changes; its implementation evidence remains recorded above.

The official source bundle is generated from the exact tagged release commit. Its external manifest records that commit, archive format, each bundled path, byte count, SHA-256 digest and Git blob identity. `SHA256SUMS.txt` covers the source ZIP and manifest. Windows script line endings follow `.gitattributes`. GitHub publication and uploaded-asset verification are recorded in the release task; the source package follows the existing local dependency-install/build workflow.
