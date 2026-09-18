# Changelog

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
