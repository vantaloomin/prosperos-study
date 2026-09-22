# v0.9.0 implementation goal: protect, bring, reuse, and publish your writing

Status: **implementation goal completed on 2026-09-22**. All four required workstreams and the integration gate are implemented and verified, including combined scheduled-backup recovery, browser flows and offline/print HTML inspection. The full backend run passed 1,948 tests; the final overlapping 30-test focused run covered subsequent hardening and two additional cases. All 113 UI-model tests, Ruff, ESLint, TypeScript/production build and whitespace checks passed. Measured evidence is in [v090-validation.md](v090-validation.md); supported behavior is in [migration-compatibility.md](migration-compatibility.md), [inspiration-compatibility.md](inspiration-compatibility.md) and [html-publishing.md](html-publishing.md). This completes the implementation and acceptance contract for the four required workstreams from the approved roadmap. The subsequent source release is documented in [v0.9.0 release notes](releases/v0.9.0.md).

## Encompassing objective

Deliver v0.9.0 as a coherent, local-first writing workflow in which an author can protect their workspace with configurable automatic backups and deliberately recover a verified saved copy; bring established writing projects into the Study through a bounded, previewable migration process that preserves originals and explains losses; create, reuse, share, and explicitly draw from weighted inspiration decks; and publish the selected Book arrangement as a standalone styled HTML manuscript. Make every workstream usable through the application, persistent across restart, compatible with existing archives and historical requests, and demonstrably respectful of author acceptance, immutable history, branch isolation, version pins, optional randomness, and the separation of private workspace data from publication. Finish with recorded implementation, recovery, integration, and browser evidence, clear supported-format limits, and no unresolved defect that prevents the required workflows.

## Baseline and working rules

- Verified starting HEAD: tagged v0.8.0, `b446ea6e01372d6a17d643f3577e072717241f3b`. Archive format at start: 51.
- Existing changes at start: modified `README.md` and untracked `ROADMAP.md`. Preserve their content; they are not implementation changes made by this goal.
- Follow the roadmap's priority order. Implement coherent slices with backend, persistence, author-facing controls, and meaningful verification before marking their acceptance complete.
- Use deterministic local conversion and selection. Reading an import, previewing a deck, restoring an archive, or exporting a Book must not call a model or execute imported content.
- Preserve original sources, earlier versions, pinned dependencies, saved inputs, recorded results, and source identity. Never infer author acceptance from imported text or a model's instructions.
- Keep local backup destinations and scheduling authority local to the installation. Importing a private archive must not silently enable a schedule or write to an imported filesystem path.
- Record scope changes explicitly. The initial goal authorized implementation. After completion, the author separately requested an official tagged GitHub source release; release preparation is documented in the release notes.

## 1. Automatic backups and recovery

Build on the existing validated private JSON archive and restore-as-new-Stories workflow.

- [x] Offer an off-by-default workspace schedule with explicit enable/disable, interval, retention count, destination, and private-sidebar inclusion controls. Show the effective destination and next due time.
- [x] Support the default workspace backup folder and an author-selected absolute local/mounted directory. Explain that the destination must be available to the running server; direct cloud account integration is outside this scope.
- [x] Run backups while the app server is running. Persist due times and perform at most one catch-up backup after downtime, rather than replaying every missed interval. Explain that a closed server cannot create scheduled copies.
- [x] Serialize backup creation, persist success/failure/interruption history, bound retries, and recover cleanly after restart. Changing or disabling settings must affect subsequent work without corrupting an in-flight copy.
- [x] Write complete validated archives atomically; incomplete files never appear as recoverable copies. Preserve the credential boundary and explicit private-conversation choice.
- [x] Apply retention only to copies owned by this workspace's automatic-backup system, after a successful new copy. Never prune manual archives, unrelated files, another workspace's copies, or the last known good copy because a new attempt failed. Keep failure details actionable.
- [x] Provide a history showing time, destination, size, scope, availability and failure status. Let the author inspect a selected copy, download it, and deliberately restore it through the established integrity checks and duplicate-safe restore receipts.
- [x] Verify actual recovered Stories, Book selections, Library versions, saved requests/results, and included source assets, including recovery into a fresh workspace. Credentials must remain absent and unfinished work must not resume automatically.

Acceptance scenarios: enable a short test schedule; create and change prose; restart; inspect successive copies; exercise retention; make the destination unavailable and recover from the error; tamper with a saved copy and reject it; restore a selected valid copy as new Stories and verify original and recovered contents independently. Exercise disabled scheduling, concurrent triggers, and an interrupted write.

## 2. Complete migration experience within an explicit compatibility matrix

One reviewable flow should connect detection, conversion, mapping, duplicate review, publication/import, and a durable compatibility receipt. A filename being accepted does not establish equivalent behavior in the source application.

### Required format targets and variants

These are implementation targets, not claims of completed compatibility. Verify each new reader against pinned primary format documentation/source and representative fixtures before accepting it. Maintain the final supported/rejected variants in a migration compatibility record.

| Area | Required targets | Conversion boundary |
| --- | --- | --- |
| Native Study material | Existing private JSON archives and portable style/recipe bundles, including supported older archive versions | Preserve existing restore/import contracts and shared identity links. |
| Conversations | SillyTavern JSONL chat exports (header plus message records); explicit role/content JSON message arrays and envelopes; UTF-8 plain text and Markdown transcripts with author-reviewed speaker mapping | Preview roles, order, timestamps and alternate/swipe material. Only deliberately selected prose becomes a new Story path. System prompts, metadata, hidden reasoning, rejected variants and notes must not silently become narrative. Ambiguous text requires mapping instead of invented roles. |
| Characters | Existing Character Card V1/V2/V3 JSON and embedded PNG; Pygmalion JSON; Backyard/Faraday legacy flat JSON; Character Card V3 `.charx` ZIP containers | Preserve card fields, greetings/examples, embedded lore and bounded local image assets. Source URIs/macros/scripts are data. No remote fetching or path execution. |
| Richer native containers | Backyard `.byaf` exported character containers, limited to inspected and documented container/schema variants | Preserve character data and supported images; report unsupported nested material. If a variant cannot be verified, reject it explicitly and document that boundary rather than guessing. |
| World info | Existing portable entry lists, SillyTavern entries-object JSON, NovelAI lorebook v3–v6, Agnai memory-book JSON, and RisuAI v1 lorebook envelopes; embedded books from supported character containers | Map supported text and rule proposals; show unsupported conditions, placement, regex, timing and ordering semantics. Entries start inactive until author review. |
| Foreign presets | SillyTavern text-completion and chat-completion preset JSON; NovelAI generation preset JSON | Convert supported instructions and sampling values into reviewable native recipe/configuration proposals. Preserve unsupported fields; do not map names to local providers, enable tools, change active settings, or start work. |

Arbitrary application databases, encrypted containers, live accounts, executable extensions, every historical export variant, and full foreign runtime emulation are outside this bounded migration promise. General DOCX/EPUB project ingestion is not required by this roadmap's transcript-and-container scope.

### Required behavior

- [x] Add a discoverable migration entry point and mixed-file batch staging with bounded file/count/container limits. Inspect content signatures and report ambiguous, malformed, or unsupported inputs individually.
- [x] Preview detected items and proposed destinations, speaker/field mappings, retained assets, original sources, duplicates, warnings, and compatibility losses before any Story or Library publication.
- [x] Preserve exact original bytes and conversion reports, with inspect/download actions and archive round-trip support. Validate nested container paths, asset sizes/types, decompression bounds and references. Accepted foreign sources travel with their published records; original native archive/bundle files remain installation-local, preserving the existing native import contract without recursively nesting old archives.
- [x] Detect exact source/content duplicates across a batch and prior imports. Same names are hints only. Default to skip/review or create new records; explicit version updates require exact target identity and current-version checks. Native-file duplicate evidence starts with migration receipts; pre-existing standalone bundle imports did not retain source bytes.
- [x] Allow selection and correction of proposed items. Clearly distinguish new items, deliberate new versions, skipped duplicates and rejected items. Provide per-item results and retry-safe receipts; a retry cannot duplicate a successful import.
- [x] Preserve transcript ordering, provenance and source role labels. New imported Stories expose the chosen mapping and selected telling; original alternate material remains inspectable. Existing Stories and their branch history stay intact.
- [x] Connect supported character attachments and lore proposals through versioned Library workflows. Publication and Story adoption remain separate explicit actions.
- [x] Keep foreign preset conversions inert until reviewed and explicitly selected. Explain unmapped variables, unsupported sampling controls, provider dependencies and semantic differences.
- [x] Test each accepted dialect and rejection path, mixed batches, same-name nonduplicates, exact duplicates, stale updates, retries, restart, and private-archive recovery. See migration checkpoints 2–6; final whole-release regression remains required.

Acceptance scenario: stage a chat, character container with artwork/world info, a foreign preset and a duplicate in one batch; inspect/correct mappings and losses; import selected items into new records; deliberately adopt reviewed resources; restart and restore the resulting workspace; verify exact source downloads, prose order and original versions without model calls.

## 3. Inspiration decks and portable collections

Existing dice tables remain supported; weighted decks need their own understandable authoring and use workflow.

- [x] Create, name, describe, duplicate, archive, edit and publish versioned decks with stable card IDs, titles, text, tags, positive weights, and explicit exclusions/disabled cards.
- [x] Define weighted selection with replacement for v0.9.0, showing each eligible card's effective probability after filters/exclusions. Reject empty eligibility and invalid/nonfinite weights. Do not imply depletion or draw-without-replacement semantics.
- [x] Offer an isolated seeded preview with transparent eligibility and odds, plus deliberate draws for inspiration. Preview cannot advance a Story, consume a live roll, change Canon or enable randomness.
- [x] Let the author choose how a drawn card is used: inspect/copy or deliberately send it into an unsent writing input; any optional integration into generation must respect the existing enabled-RNG ceiling, explicit selection and request-freezing rules.
- [x] Persist real draw receipts with deck version, eligible population/filter decisions and recorded outcome. Replay/retry/restore reuse that result; later edits do not reroll history.
- [x] Provide versioned, bounded portable deck/collection import/export with preview, duplicate decisions, dependency/compatibility reports and preserved unsupported metadata. No credentials, private conversations or unrelated Stories enter a pack.
- [x] Include editable genre/situation starter packs (for example quiet character moments, mystery complications and speculative encounters) with useful card content and clear selection behavior. Importing a starter does not enable it in any Story.
- [x] Preserve versions, references and recorded outcomes through restart and private-archive restoration. Verify pack round trips, odds/filter arithmetic, disabled randomness, retries and branch separation.

Acceptance scenario: create and weight a deck; exclude a card and inspect changed odds; preview without touching Story state; record a deliberate draw and use it in an unsent input; revise the deck; export/import a collection into a clean workspace; verify the old receipt and saved request still use their original version and outcome.

## 4. Standalone styled HTML publishing

- [x] Add HTML beside DOCX and EPUB in the Book export flow, using the same selected chapter/scene arrangement and telling resolution.
- [x] Produce a UTF-8 standalone document with embedded CSS, semantic headings, title/publication metadata, optional contents navigation, readable responsive typography and print styles. Reading must not require the Study, network assets or JavaScript.
- [x] Safely render supported prose formatting; escape raw markup and prevent active content, executable URLs or private/internal records from leaking through metadata or text rendering.
- [x] Export only selected publication prose and explicit publication metadata. Exclude author notes, private conversations, prompts, model inputs, branch diagnostics and unselected tellings.
- [x] Verify chapter/scene order, Unicode, titles, selected historical tellings, empty/missing selections and long paragraphs; inspect desktop/narrow/print rendering and open the file outside the app.

Acceptance scenario: assemble a Book from scenes on different selected tellings; export all three publication formats; compare the selected prose/order; read the HTML offline at desktop and narrow widths; inspect its source for accidental internal data or active content.

## Integration and completion gate

- [x] Preserve existing v0.8.0 writing flows, styles/recipes, Companion edits, Book selections, library source files and immutable request histories.
- [x] Add explicit schema/archive migrations only as needed; retain old-archive fixtures and verify new data through export, fresh-workspace restore and re-export. Installation-local scheduling is never activated by import.
- [x] Run relevant focused backend and UI-model tests for each slice. Before completion run the complete backend/UI-model suites, Ruff, ESLint, TypeScript/production build and whitespace checks, fixing relevant failures.
- [x] Exercise actual author-facing flows in an isolated browser workspace: success, validation failure, recovery, keyboard/focus, narrow layout, enlarged text and reduced motion where affected. State the precise coverage.
- [x] Record measured results and unresolved checks in `v090-validation.md`, with reproducible commands/fixtures. Keep old release counts, current deterministic checks, browser evidence and any live-provider evidence separate.
- [x] Update product/help and compatibility documentation for actual delivered behavior and known limits. Mark checklist items complete only with evidence.

Required v1.0 packaging, native macOS acceptance, broad provider coverage, demanding-branch performance and long-manuscript quality remain allocated to v1.0. Research collections remain a candidate; passage-splicing, advanced repetition/pacing, audio/phone access, generated imagery and Date Mode remain outside this goal.

The goal is complete only when all four required workstreams and the integration gate are delivered and verified. A partial implementation checkpoint leaves the goal active.

## Initial implementation sequence

1. Automatic-backup settings, durable scheduling/history and safe filesystem lifecycle; connect recovery to the existing archive review/restore path; verify the author-facing flow.
2. Migration staging/reporting and transcript import, then bounded containers/assets, preset proposals and batch/deduplication; verify the matrix and round trips.
3. Versioned weighted decks, isolated previews, explicit draw receipts and portable packs; verify state/recorded-result boundaries.
4. HTML Book export and final cross-workstream regression, browser checks and documentation.
