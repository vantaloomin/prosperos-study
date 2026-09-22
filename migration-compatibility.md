# v0.9 migration compatibility

The v0.9 implementation and acceptance gates are complete; measured evidence is in [v090-validation.md](v090-validation.md). Compatibility is limited to the formats and mappings below. Imports run locally, preserve their original bytes, and never execute foreign scripts or fetch referenced URLs.

## Verified character containers

Library → Import file now accepts the following bounded containers alongside the existing Markdown, SGC, Character Card JSON/PNG, legacy native-character and world-info readers.

| Container | Accepted mapping | Retained as reference |
| --- | --- | --- |
| CHARX | Root `card.json`, Character Card V3 / spec version `3.0`; character fields, individual greetings, embedded lore proposals; declared PNG/JPEG/WebP images, with an explicit artwork choice | Other local media, external/default URIs, unknown files, macros, extensions and unsupported runtime rules. The exact original ZIP retains all files. |
| BYAF | Root `manifest.json`, schema version 1, one character, 1–32 referenced scenarios. Character persona and lore items; narrative/examples from the first listed scenario; supported character greetings across scenarios; declared PNG/JPEG/WebP artwork | Every manifest, character and scenario document, including conversation histories, generation settings and additional scenarios. BYAF conversation history does not become a Story through the character importer. GIF and other unsupported media remain downloadable references. |

The preview identifies the mapping, limitations, missing/unsupported assets and editable fields before publication. Lore-entry rule proposals remain inactive until reviewed; publishing a Library item does not adopt it into a Story. Source downloads and supported images remain available after archive restoration, including images the author did not choose as the portrait.

Bounds: 10 MiB upload, 256 ZIP entries, 10 MiB per expanded entry, 32 MiB total expansion, and 64 declared assets/images. Only stored/deflated ZIP entries are accepted. Encrypted entries, links, special files, traversal, absolute/drive paths, ambiguous names and case-colliding paths are rejected. Damaged compressed data is an import error. Files are inspected in memory; source paths are never extraction destinations. Image rendering uses the existing validated local artwork pipeline.

BYAF validation covers the required v1 fields and the bounded shapes used by this converter. It is not a general JSON Schema engine, a database importer, or an implementation of every Backyard export version. Unknown fields are preserved rather than enabled.

## Pinned primary references

- [Character Card V3 specification](https://github.com/kwaroran/character-card-spec-v3/blob/f3a86af019fbd99f788f7a1155f399655b34ab35/SPEC_V3.md), commit `f3a86af019fbd99f788f7a1155f399655b34ab35`. The specification's local asset scheme is spelled `embeded://`.
- [BYAF v1 schemas](https://github.com/backyardai/byaf/tree/7ebf2fdbb06a36b4f900a8de45480c4a2965df03/schemas/v1), commit `7ebf2fdbb06a36b4f900a8de45480c4a2965df03`: manifest, character and scenario schemas.
- [SillyTavern chat import/export source](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/src/endpoints/chats.js), pinned release commit `06bde939fb1e9c4c8d8641d810f0a916b5bce127`.

## Transcript migration

Library → **Migrate writing → Mixed files** accepts transcripts alongside other supported formats. The **Transcripts** tab also stages a single transcript. Choose the message roles, select an alternate reply where present, give the new Story a title, and acknowledge the review before importing. Accepted messages keep source order. They create a separate Story; no existing Story is appended to or overwritten. Import performs no model work and starts the new Story with randomness disabled.

| Dialect | Supported shape | Limits and review |
| --- | --- | --- |
| SillyTavern `.jsonl` | Export header containing `chat_metadata`, `user_name` or `character_name`; message objects with string `mes`, boolean `is_user`, optional boolean `is_system`, speaker name, timestamp and string `swipes` | `mes` is the proposed current telling. Distinct swipe texts are alternatives for explicit selection. Swipe IDs, metadata and reasoning are retained in the exact original rather than interpreted as acceptance. Group/runtime behavior is not emulated. |
| Role/content JSON | Array of objects, or object with a `messages` array; string `role` and string `content`; optional `name`, `timestamp` and string `alternatives` | User/human, assistant, narrator and OOC roles are proposals. Unknown roles begin skipped. System/developer/tool/function roles are locked to reference only. Multimodal content arrays are rejected rather than flattened. |
| UTF-8 `.txt`, `.md`, `.markdown` | Proposed blocks at `Speaker: text` lines or level 2–6 Markdown headings; unlabelled text is an Unassigned block | Every block begins as reference only. The author explicitly maps speakers and reviews boundaries. Outer block whitespace and speaker/heading delimiters are removed from proposed prose; exact source bytes remain available. This is a bounded transcript parser, not a general Markdown-document or application-database importer. |

Bounds: 10 MiB source, 1–2,000 messages, 100,000 characters per message/variant, 100 extra alternatives per message, and 5 million total message/variant characters. Invalid UTF-8, duplicate JSON keys, nonfinite JSON numbers, NUL text, malformed flags and unsupported content shapes are rejected before any Story is created. Review pages show 20 messages at a time without truncating their selected text.

System/tool instructions, metadata, embedded attachments and unchosen replies never silently become prose. Text files have no trusted role schema: all blocks require explicit author mapping. Timestamps remain source labels, not event dates. Inline markup and macros remain literal data during conversion. The complete original, including private source metadata, is included in the imported Story's private archive; public prose exports exclude it.

Exact source hashes and normalized full-message-content hashes identify prior transcript imports. A content match can have different source metadata, which the preview states. Same names do not identify duplicates. The default decision skips a prior match; deliberately creating another Story is explicit. This is duplicate review across imported transcripts, not an assertion that their chosen Story tellings are identical. Operation IDs make retries reuse the same result.

**Story setup → Preserved migration sources** provides exact downloads and inspection of original roles, timestamps, all alternatives and recorded choices. Source bytes, reports, original accepted nodes and mappings survive restart and private-archive restoration. Archive format **52** introduced migration sources/receipts; format **53** adds preset origins and keeps the upgrade paths from formats 1–52. Sources staged but never imported remain local and are not included in private archives. Browser-only unsubmitted mapping edits are also outside an archive.

## Foreign generation presets

Library → **Migrate writing → Generation presets** accepts a bounded JSON file, preserves the exact original, and previews instruction fragments and sampling proposals. Instructions and sampling selections begin empty. Select fragments, explicitly replace the editable recipe text with them, correct that text, review the destination and acknowledge compatibility before publishing. Foreign macros remain literal text even when the native recipe is later selected for writing. Foreign prompt roles, order, depth, enable switches and runtime conditions are not reproduced.

| Dialect | Recognized shape | Mapping |
| --- | --- | --- |
| SillyTavern text-completion preset | Object with `temp`, `top_k`, `top_p`, `rep_pen` | Supported temperature, top-p/top-k/min-p and penalty proposals. Templates and extensions remain original-file reference. |
| SillyTavern chat-completion preset | `temperature` plus `openai_max_tokens`, `prompts` or `prompt_order` | Sampling proposals, legacy named prompt fields, and `prompts` records with string `content`. All fragments need author selection; source runtime ordering is not applied. |
| NovelAI v3 preset envelope | Integer `presetVersion: 3` and object `parameters` | Recognized sampler proposals and `max_length` as a proposed output limit. No portable instruction schema is assumed. Other preset versions are rejected. |

Bounds: 1 MiB, nesting depth at most 40, at most 128 prompt records plus five legacy prompt fields, and a final native instruction limit of 12,000 characters including literal-brace escaping. Duplicate JSON keys, nonfinite JSON numbers, ambiguous dialects and known nonempty credential fields are rejected. Unsupported parameter types/ranges remain reference-only without clamping. Specialized samplers, tokenizer biases, stop/prefill rules, source provider/model names, URLs and extensions never configure a connection.

Selected sampling fields require an explicitly chosen **local model profile and its current version**. The preview shows each previous and proposed value and runs the existing provider/model capability validation. Publication creates a separate profile using that local configuration, without copying its saved key, making it Primary Writer, assigning it to a Story, or adding a recipe step. The author can later choose that profile through the ordinary model controls. Equivalent sampling numbers do not establish equivalent model behavior.

Exact-source and equivalent-proposal hashes identify previous preset imports. Skip is the default for matches; another new recipe requires an explicit decision. Updating a recipe requires its exact identity and current version. Same names are not identity. Retries reuse the saved publication result. Earlier recipe versions and pins remain unchanged.

Published recipe versions expose their exact source downloads and reviewed receipt in the editor and version history. Private archives retain accepted source bytes, reports, selections, the copied configuration and its local base-profile version. Restores remap identities and validate that the receipt matches the recipe and configuration. Portable writing bundles carry reviewed native guidance and inert sampling proposals; they do not embed the original source or foreign connection values. Unpublished staging and browser draft choices are not portable archive records.

Primary source shapes were inspected in [SillyTavern preset-manager.js](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/preset-manager.js), [openai.js](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/openai.js), [textgen-settings.js](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/textgen-settings.js), and [nai-settings.js](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/nai-settings.js), all pinned to the same commit. [NovelAI sampling documentation](https://docs.novelai.net/en/text/editor/slidersettings/) describes model-dependent sampling behavior.

## Mixed-file review and recovery

Library → **Migrate writing → Mixed files** accepts 1–20 files, at most 10 MiB each and 32 MiB total. Presets retain their 1 MiB limit; native writing bundles retain their 8 MiB limit. Larger private archives use Settings → Backups & recovery (128 MiB). The queue inspects signatures, retains valid interpretations, and reports malformed/unsupported files individually. Text that could be a transcript or Canon needs an explicit interpretation before mapping. A reader may use a normalized extension; the batch download keeps the exact original bytes and filename.

Review and publish each included file explicitly. The queue reuses the detailed transcript, Character/Canon, preset, archive and writing-bundle reviews. Unknown metadata stays reference material. Omit a file without affecting its neighbors. Queued exact-source and equivalent-proposal matches are visible before publication; publication rechecks successful prior imports and defaults to skipping matches. A matching name alone never selects a target. Native archive/bundle matches use completed migration receipts; older standalone bundle imports had no retained source file and cannot be inferred from names.

Each file has a durable result/report and frozen publication choices. An interrupted publication can be retried after restart: a committed leaf-operation receipt is reused even if a temporary native archive file subsequently disappears. Correctable validation failures return the item to review. A successful item cannot be published again by retrying, and changes to frozen choices are rejected. Restoration and import start no background generation.

Queues, unfinished staging, browser review drafts and original native archive/bundle files stay on this installation. Accepted **foreign** source bytes and provenance travel with the imported Story or Library versions in private archives and can be downloaded after recovery. Native imports retain their established record-level contracts: backups do not recursively nest old archive files. Download an original native file from the queue when retaining that exact envelope is important. Rejected bytes are not retained, including rejected credential-bearing preset files.

These supported dialects do not establish compatibility with arbitrary historical variants or application databases. See [the encompassing goal](v090-implementation-goal.md) and [measured evidence](v090-validation.md).

## Character and Canon duplicate review

Library imports now compare each proposed character/Canon part with prior published imports. Exact original bytes and equivalent proposed content are separate match labels. Names and unsupported source metadata do not enter the proposal-content comparison. This does not compare later author edits or treat two resources as interchangeable. The preview shows up to 50 matching versions per part; the server rechecks at publication to handle another import made after the preview.

Matched parts default to skip. The author can deliberately create a new item or select an exact existing identity for a current-version update. Mixed results list new versions and skipped parts separately. If a Canon proposal is skipped while a new character is published, it is not automatically linked to an existing Canon version; the author can select that collection in the character editor. Selecting and publishing both new parts still links their newly published versions through the established importer.

Deduplication uses immutable original reports and published source links, so evidence survives private-archive restoration. Unpublished staging alone is not treated as a previous import. Legacy operation fingerprints remain replayable. Same-source imports made through separate new operations use the new duplicate-review policy.
