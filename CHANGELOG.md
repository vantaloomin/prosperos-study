# Changelog

## v0.9.0 - 2026-09-22

Protect, bring, reuse, and publish your writing. Application version: **0.9.0**.

- Configurable automatic workspace backups start off and run while the server is open. Choose an interval, retention and destination; inspect saved copies and failures; verify a copy before deliberate recovery as new Stories. Retention protects manual copies and unrelated files, and imported archives cannot activate a schedule.
- A durable mixed-file migration queue connects format detection, detailed review, duplicate choices and independent publication. Added bounded CHARX/BYAF character containers, supported transcript migration and inert preset conversion preserve originals and recover interrupted publication. Foreign instructions, credentials and runtime behavior never gain authority through import.
- Versioned weighted inspiration decks provide exact odds, tags/exclusions, isolated seeded previews, explicit recorded draws, history, editable starters and portable reviewed collections. Story handoff appends to unsent input without sending, accepting Canon or enabling Story randomness.
- Book publishing adds standalone HTML beside DOCX and EPUB, using the same frozen selection. Optional contents and embedded reading/print styles work offline; selected prose and publication metadata are separated from private workspace records.
- Private archive format **54** preserves accepted migration sources, deck versions, draw receipts and collection origins. Historical inputs and selected prose remain intact across restore; installation-local schedules, queues and prepared downloads remain local.

The full backend gate passed **1,948 tests**; a later overlapping **30-test focused run** covered final hardening and two additional cases. All **113 UI-model tests**, Ruff, ESLint, TypeScript and the production build passed. Rendered-browser checks cover the four workstreams, recovery, narrow/enlarged layouts, offline reading and a four-page print preview. See [release notes](releases/v0.9.0.md) and [measured validation](v090-validation.md) for scope and limits. The [tagged source release](https://github.com/vantaloomin/prosperos-study/releases/tag/v0.9.0) includes the source ZIP, per-file manifest and SHA-256 checksums.

## v0.8.0 - 2026-09-21

Personal writing tools and an editable Sidebar Companion. Application version: **0.8.0**.

- **Skip setup** opens the writing area directly from any unfinished wizard step. Entered choices and selected Library versions are retained; empty titles become **Untitled Story**. Manual writing needs no model, and saved-request recovery prevents duplicate Stories after a lost response.
- Versioned writing styles, author examples, explicit sample analysis, per-Story pins, and per-request overrides guide supported prose and revision tasks without changing factual memory or source authority.
- Portable writing recipes include typed inputs, models, task switches, reader lenses, optional styles and chance settings. Complete previews and explicit per-step execution retain frozen inputs, reports, attempts, and editable final proposals. Importing or browsing starts no work.
- Compare tellings, favorite and archive branches reversibly, and search across paths with archived-source filtering. Curation and edits preserve existing manuscript selections.
- The Collaborator now has a genuine Pop Out, pinned selections/comparisons, focused text tasks, scoped application permission, and rename/search/archive controls. Concurrent views protect unsent wording and recover saved operations without automatic resending.
- Shared text proposals support add/insert/replace/update, conflict review, immutable accepted-passage revisions with preserved suffixes, versioned Library/prompt edits, application receipts and Undo.
- Archive format **51** preserves the new resources and workflows alongside existing manuscripts and memory. Historical requests retain their exact provider-input bytes through migration and restore. Private discussion inclusion remains explicit; restore never replays calls or edits.

Before the Skip setup addition, the full pipeline passed **1,756 backend tests**, **110 UI-model tests**, Ruff, ESLint, TypeScript and the production build. The addition passed **113 UI-model tests**, **7 onboarding backend tests**, **24 browser checks**, ESLint, TypeScript and a fresh production build; the full backend suite was not rerun for this frontend change. Combined acceptance and rendered-browser/restart checks passed in the earlier implementation; [representative live-output evaluation](v080-output-evaluation.md) records 15 calls, explicit retries and author corrections. See [v0.8.0 release notes](releases/v0.8.0.md), [validation evidence](v080-validation.md) and [the Skip setup goal](v080-skip-setup-goal.md) for results and limits. The [tagged source release](https://github.com/vantaloomin/prosperos-study/releases/tag/v0.8.0) includes a source ZIP, file manifest and SHA-256 checksums.

## v0.7.5 - Unreleased

Optional story recall, reviewable corrections, and reading-time preparation. Application version: **0.7.5**. Includes the published v0.7 manuscript, model-control, and agent-template features.

- **Memory readiness** in Writing tools shows the selected writer's local recall, prewriting search, semantic configuration, relationship-link dependencies, and automatic link preparation. Direct controls open the relevant preferences, model profile, or source links. Automatic links identify their separate Story writer. Checking readiness makes no model calls and does not rate narrative accuracy.
- **Check earlier evidence before writing**, off by default, adds one bounded planning request per writer candidate, up to two searches and eight exact passages within the saved context allowance. Optional semantic search combines independent keyword and embedding rankings; missing setup, incomplete cache warming, or failure retains keyword search. The explicit Nomic input format separates query and document prefixes.
- **Tentative relationship links**, off by default, connect source-quoted promises, handoffs, outcomes, testimony, and knowledge claims for retrieval. Prepare existing passages explicitly, or separately enable preparation after acceptance on a connection with verified interruption. Links never promote interpretations into accepted facts or completed plans.
- Recall receipts retain search decisions, group coverage, exact final inputs, timing and usage. Current recall v6 includes frozen mode/agency guidance in budget accounting and protects relevant evidence already in context. Saved v1-v5 requests retain their original packing behavior.
- **Revise continuity** proposes one alternative to an unaccepted draft using its complete saved evidence and profile. The original remains available; only Keep accepts a telling. Revision v2 includes frozen mode/agency instructions and the profile's safety margin, while v1 remains replayable. Over-budget requests fail without dropping sources. Automatic continuity checking remains experimental.
- **Phrase check** finds recurring exact wording locally and links to source passages. Optional **Automated cleanup** can make one bounded polishing request per flagged draft. Original and cleaned wording remain selectable; cleanup cannot silently rewrite accepted prose.
- **While I read** preparation yields to foreground writing, supports acknowledged interruption on verified LM Studio native connections, and separates preparation, queueing, first text and cleanup timings. Local chunk/index warming makes no model requests. Unsupported or unverified connections keep explicit preparation and cleanup-before-ready available.
- **Broader Library imports** cover Pygmalion and Backyard/Faraday legacy characters plus supported portable, SillyTavern, NovelAI, Agnai and RisuAI lorebooks. Import previews preserve original files and unknown metadata; proposed native entries remain off until enabled. Foreign execution rules are not treated as equivalent.
- **Archive format 37** preserves manuscripts, bookmarks, mode guidance, cleanup, relationship links and revision receipts together. Strict migration distinguishes published and development archives that independently used formats 32/33. Restores preserve original request bytes, remap references, and leave automation off without resending model work.
- **Illustrated agent and memory guides** in the README explain Narrative/Passive and Roleplay/Active, including optional recall, character scope, and author acceptance. Each guide expands inline and links to its full-size image.

Validation: the complete final-tree check passed **1,374 backend tests**, **94 UI-model tests**, Ruff, ESLint, TypeScript, and the production build. Desktop/mobile browser checks covered readiness controls, explicit continuity revision, and a restored v0.7.0 manuscript. An isolated restore → write → revise → keep → fork → restart → export/restore exercise passed with a controlled provider. Two upstream test-client deprecation warnings remain. See [the release-readiness goal](v075-release-readiness-goal.md) for exact evidence and the archive compatibility correction.

These lifecycle checks do not establish live narrative quality. The [consolidation audit](narrative-reliability-audit.md) records earlier retrieval improvements and remaining writer errors; supplying relevant evidence does not guarantee correct long-form continuity. Earlier feature checks and their limitations remain in [historical development validation](v075-development-validation.md).

## v0.7 - 2026-09-18

Manuscript organization, model controls, and Active/Passive Agent Templates. Application version: **0.7.0**.

- **Book workspace:** organize chapters and named scenes, reorder or move scenes between chapters, and select each scene's telling and passage range. Selections preserve a fixed point on their source path. Read in manuscript order, bookmark passages, and search across all saved chapters. Organization changes have explicit Save/Discard controls and a local draft.
- **Publishing:** prepare fixed DOCX and EPUB 3 downloads with title, author, language, chapter order, and optional scene headings. DOCX uses editable heading styles, chapter breaks, and page numbers; EPUB provides linked contents and a reading spine. Publication files contain selected prose only, with an option to include character contributions. Author notes, bookmarks, and private model/context records are excluded.
- **Model profiles:** adapter-specific reasoning effort, thinking modes and budgets, response reserve, output-parameter choice, verbosity, sampling overrides, and context safety margin. Reported model capacities and supported settings are validated; unknown capabilities remain explicit. Thinking budgets cannot consume the reserved response space. Existing profile settings remain the inputs for exact retries.
- **Usage:** readable provider-reported token counts and cost alongside raw reports, including failed output-limit attempts and individual character requests. Missing values stay unknown. Thinking and partial prose survive output-limit failures; the next step explains how to adjust settings and start a new request.
- **Agent Templates:** new Passive Stories enable the full workflow; Active starts with the writer, Collaborator, background planning, and Scribe memory tasks. Per-Story switches and explicit template application respect workspace disables. Existing switches are preserved when experience changes.
- **Mode guidance:** editable, versioned mode and agency sections compose around supported role prompts. Agency is independent of Active/Passive mode. Persona names and section versions are frozen for exact replay; blind readers, Scribe, Collaborator, and triage retain their scoped instructions. Custom role prompts and Story pins are preserved, and Stories can opt out of composition.
- **Archive format 33:** manuscript organization, bookmarks, and prompt sections restore with remapped references and unchanged recorded provider inputs. Older archive formats migrate additively.

Validation: the full backend suite passed **1,190 tests**. Final manuscript compatibility and validation fixes then passed **61 targeted tests**, including the new removed-passage selection case. All **86 UI-model tests**, Ruff, ESLint, TypeScript, and the production build passed. Two upstream Starlette/AnyIO test-client deprecation warnings remain.

Browser validation used isolated Chrome on Windows at desktop and 390px mobile sizes, with synthetic provider responses. Checks covered manuscript ordering, alternate tellings, bookmarks, search, draft recovery, downloads, agent customization, workspace ceilings, prompt edits, saved model controls, budget validation, usage, and failed-request retry. Two DOCX samples were rendered in LibreOffice and all seven pages visually inspected. Two EPUB packages passed ZIP, XML, manifest, reading-order, and link checks; their XHTML navigation and escaped prose were checked in Chrome. Live provider behavior and dedicated ebook-reader compatibility remain unverified.

## v0.6.2 - 2026-09-18

Agent workflow consolidation. Application version: **0.6.2**.

- Eleven roles replace the 31 specialist cards. Scene planner handles options, beats, and private background; Scribe handles continuity, memory summaries, Canon aids, and beat preparation; Library assistant handles drafting, critique, and tightening. Each task retains its validation and authority boundaries.
- Two readers offer selectable lenses. The independent reader sees the proposed prose and at most two preceding prose contributions. The informed reader receives permitted references and checks approved beat coverage. Findings retain lens names and exact source quotations; comparisons remain explicit.
- New scenes skip the separate continuity brief, coverage call, verification call, dialogue patch, and patch-check call. Triage checks claims against supplied evidence and leaves undecidable claims for the author. One patch can revise prose and dialogue. Selecting it records the author's choice; it does not claim an additional model check. Plan, revision package, and scene acceptance still require explicit decisions.
- Optional beat assessment runs after accepted prose. Writing starts immediately, using a ready result for that exact Story state when available. Pending, failed, stopped, or stale preparation cannot attach itself later to a writing request. Frozen retries and inspected preparation history remain available.
- Prompts and routing expose combined roles and retained task settings. Custom prompt versions, explicit Story pins, model assignments, and disabled tasks survive the update. Adopting combined instructions is deliberate. Historical scenes and specialist reports remain readable with their original stage names and inputs.
- Archive format 32 adds combined defaults without replacing historical prompt versions or recorded request bytes. Older formats migrate additively. Model input and output remain JSON; the experimental XML memory protocol is not adopted.

Validation: the full backend suite passed 1,120 tests. The final prompt-identity and historical-scene compatibility changes then passed 122 targeted checks, including ten new cases. All 86 UI-model tests, Ruff, ESLint, TypeScript, and the production build passed. Two upstream Starlette/AnyIO test-client deprecation warnings remain.

Browser validation used isolated Chrome and deterministic protocol fixtures: a fresh scene completed in nine model calls, desktop and 390px layouts passed overflow checks with reduced motion, and a delayed assessment did not delay the next draft. Prompt editing, role routing, reader setup, approval, acceptance, keyboard dismissal, and focus return were exercised. These checks do not establish live-model output quality or provider latency.

## v0.6.1 - 2026-09-18

First-user feedback update. Application version: **0.6.1**.

- Generated drafts appear inline, with explicit Keep, Keep on new branch, Try another, Dismiss, and expanded details. Status shows observed stages, model identity, elapsed time, and Stop. Save/continuation recovery checks durable operation receipts; frozen retries retain earlier attempts and partial output.
- Author’s note has a separate composer control. Story setup, Story brief, and Scene goal labels distinguish story-wide guidance from path notes and scene planning.
- Stories collapse when a story opens. Shared icon tooltips support pointer and keyboard use; Context opens as a wide reference dialog.
- Collaborator shows its resolved connection and saved routing. Docked, movable floating, and full-workspace layouts retain conversation state; numeric geometry controls supplement dragging. Connection management returns to the conversation.
- API tokens use explicit visible Add/Replace entry. Interface sizing extends through 200%, preserving legacy sizes. Checked states are clear, and randomness edits identify unsaved changes. Custom palettes include color pickers, hex entry, contrast feedback, preview, and reset.
- Passage removal creates an immutable revised path, an omission marker, and Undo. Later prose remains in order, and originals remain on the source path. Effective context, retrieval, and readable exports exclude omissions. Dependent state after the changed passage is excluded from the revision; the author explicitly acknowledges returning to the prior state before continuing. No rolls or model calls are replayed.
- Archive format 31 adds generation activity and path-revision provenance. Older format fixtures retain their original record groups and migrate additively. Historical provider inputs remain unchanged.
- Reading positions survive inline streaming, middle-passage revisions, and Collaborator layout changes. Narrow layouts provide a labeled Tools menu and scrollable enlarged controls.

Validation: 1,092 backend tests and 86 UI-model tests passed, along with Ruff, ESLint, TypeScript, and the production build. Isolated Chrome checks covered delayed/failed/buffered responses, restart and reload recovery, simultaneous recovery from two tabs, inline acceptance, removal/Undo, Collaborator modes, token entry, palettes, randomness saves, and nine viewport/interface-size combinations. Native Chrome 200% page zoom was checked separately. The author confirmed no password suggestions in the regular-Chrome Add API key flow; Bitwarden was unavailable.

The 240-passage branch-switch fixture met the existing 1.5-second target in both directions. This does not resolve the prior worst-case performance backlog. Synthetic provider results are not a live NIM check; broad accessibility conformance and native macOS acceptance remain unverified. No live provider or personal story database was used for this validation.

## v0.6 - 2026-09-18

Memory management preview. Application version: **0.6.0**.

### Added

- **Long story memory:** optional local retrieval of earlier accepted prose and relevant Canon within the selected model's context allowance. Recent prose, required guidance, source order, and branch boundaries are retained; the complete manuscript remains stored.
- **Plans and commitments:** record intentions separately from outcomes, track each participant, and preserve postponements, attempts, withdrawals, supporting passages, and edit history. Forks retain the applicable memory state.
- **Optional plan review:** use the existing continuity prompt and model configuration to suggest changes from accepted passages. Suggestions require explicit acceptance; manual bookkeeping needs no model call.
- **Inspectable memory:** preview supplied sources and coverage, manage recall decisions, follow evidence back to the manuscript, and preserve character knowledge boundaries.
- **Reviewed summaries and Canon cues:** optional preparation, review, and maintenance workflows for longer material. Model preparation is separate from local retrieval and can be disabled.
- **Archive verification:** preserve saved inputs, source identities, accepted memory, reviews, and attempts through backup/restore. Older archives report when complete historical verification is unavailable.
- **LM Studio native connections:** model discovery and supported per-profile thinking controls alongside the existing OpenAI-compatible connection.

### Using memory

Choose **Story details > Story memory > Long story**. Full history remains the default when no memory preference has been set. Manage plans under **Context > Memory**; prepare optional summaries under **Writing tools > Story memory**. Author acceptance controls what becomes recorded memory.

Before updating, save a workspace backup, stop the app, retain the `data/` folder, update the source, and rerun `install.bat` or `bash install.sh`. New archives contain memory records and require a compatible app version; keep the pre-update backup if you may return to v0.5.

### Preview limits

- Recall is selective. Existing evaluations show missed causal, temporal, and indirect evidence; the product scorer has not demonstrated an advantage over TF-IDF on the current small corpus. Supplying evidence is not proof of a correct generated answer.
- Plan and summary interpretation can be wrong. Exact quotation checks establish provenance, not semantic correctness. Plans do not automatically complete when time passes.
- The XML summary experiments remain evaluation tooling. Default application memory I/O is unchanged; XML is not a new user-facing memory mode.
- Worst-case branch-switch performance, broad accessibility conformance, and native macOS installation/Keychain acceptance remain unfinished. The production build still reports a main-bundle size warning.
- Companion Mode, social feeds, built-in image generation, and scheduled backups remain future work.

## v0.5 - 2026-09-17

Initial early preview: writing and roleplay, branching stories, versioned Characters and Canon, a separate sidebar collaborator, configurable providers and prompts, optional narrative tables, exports, and local backups. The subsequent macOS launcher update added shell installation and launch scripts.
