# Changelog

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
