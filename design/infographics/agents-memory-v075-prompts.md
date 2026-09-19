# Agents and long memory infographic prompts

Generated with the built-in image_gen tool for the current v0.7.5 implementation.

Source check: server/agent_templates.py, server/roles.py, server/story_mode.py, server/section_prompts.py, server/generation_context.py, server/memory/knowledge_writer.py, README.md, design/brand.md.

## Narrative / Passive

Use case: infographic-diagram.
Create ONE polished, finished editorial infographic for Prospero’s Study, explaining the actual v0.7.5 implementation. High-resolution portrait poster, approximately 3:4 aspect ratio. This is one of a coordinated pair. Professional information design, generous breathing room, meticulously aligned grids, large readable text, elegant Literata-like serif headlines and IBM Plex Sans-like body labels. Brand colors only: ink #191816, parchment #ede5d6, brass #c5a46d, subtle tints. Quiet literary writing room, subtle theatrical proscenium framing; no curtains, masks, robot mascots, brains, neon, sci-fi UI, logos of providers, watermarks, fake metrics or invented UI screenshots. Fine pen-line illustrations of manuscripts, source cards, bookmarks and a branching path, integrated functionally. Use a small fountain-pen-nib inside a simple arch as a discreet emblem. Prioritize legibility and explanatory arrows over decoration. Render all supplied visible text accurately and completely. No invented facts or labels. Agent role names must be readable. Small footer text must still be comfortably legible. Distinguish human decisions from model tasks and local memory processing with consistent shapes and a compact legend. Clear arrows, no crisscrossing, never imply that an AI suggestion automatically becomes accepted history. Do not render these art-direction instructions.

PALETTE: light parchment background, ink typography, brass rules and decision accents. Airy premium book-design aesthetic. Five vertically organized areas: title, ordinary turn loop, memory architecture, optional scene team, compact footer. The MEMORY area is the visual centerpiece. Do not merge separate areas into an untraceable flow.

VISIBLE TEXT AND LAYOUT:

HEADER:
"PROSPERO’S STUDY"
"Narrative / Passive"
"You direct the story. Agents help shape the telling."
Small edition label: "v0.7.5 • Agent & memory guide"

A. Main loop, five clear steps with arrows:
"Your direction" → "Memory packet" → "Primary prose" → "Review draft" → "Keep or branch"
Small caption: "Generated prose enters accepted history only when you choose Keep."

B. Large central section: "Long memory: keep the archive, select the evidence"
Show a saved archive feeding a smaller bounded context packet. A return arrow from Keep feeds the accepted path.
Archive/source cards:
"Accepted path" / "Recent and earlier prose"
"Canon & characters" / "Story-pinned versions"
"Plans & commitments" / "Explicit states and evidence"

Bounded packet:
"Context that fits"
"Recent prose + relevant originals"
"Author notes + required Canon + plans"
Small local-processing badge: "Local keyword recall • no extra model call"
Clearly marked optional rail, feeding the packet:
"OPTIONAL AIDS"
"Prewriting search" / "One planning call before a draft"
"Semantic search" / "Embeddings support keyword search"
"Relationship links" / "Tentative links return source passages"
"Reviewed summaries" / "Help locate original evidence"
Caption: "Choose Long story. Extra recall aids start off."
Scope note: "Prewriting search applies to ordinary Author-view drafts, not scene or character-lens requests."
Small receipt card at the packet exit: "Draft receipt: exact inputs, sources, coverage and fallback"

C. Agent teamwork: "A full scene team, when you choose it"
Caption: "Passive enables these roles; they do not all run on every turn."
Two tidy rows forming a single ordered route. Include human checkpoints as small brass diamonds rather than extra agent boxes:
"Scene planner" → human "Approve beats" → "Scene draft + Dialogue writer" → "Independent reader + Informed reader" → "Review triage" → human "Approve changes" → "Revision patch" → "Scribe" → human "Accept scene"
One short explanatory line under Scribe: "Proposes continuity"
A separate slim support rail:
"Collaborator: discuss and retrieve; never advances the story."
"Library assistant: proposes reference edits."

D. Compact footer, three short guardrails, visually separated:
"Accepted history stays branch-specific."
"Links and summaries are aids, not new facts."
"Evidence improves recall; the writer can still make continuity errors."
Final small caption:
"Templates are editable. Workspace switches still apply."
Legend: "Human choice • Model task • Local memory"


## Roleplay / Active

Use case: infographic-diagram.
Create ONE polished, finished editorial infographic for Prospero’s Study, explaining the actual v0.7.5 implementation. High-resolution portrait poster, approximately 3:4 aspect ratio. This is one of a coordinated pair. Professional information design, generous breathing room, meticulously aligned grids, large readable text, elegant Literata-like serif headlines and IBM Plex Sans-like body labels. Brand colors only: ink #191816, parchment #ede5d6, brass #c5a46d, subtle tints. Quiet literary writing room, subtle theatrical proscenium framing; no curtains, masks, robot mascots, brains, neon, sci-fi UI, logos of providers, watermarks, fake metrics or invented UI screenshots. Fine pen-line illustrations of manuscripts, source cards, bookmarks and a branching path, integrated functionally. Use a small fountain-pen-nib inside a simple arch as a discreet emblem. Prioritize legibility and explanatory arrows over decoration. Render all supplied visible text accurately and completely. No invented facts or labels. Agent role names must be readable. Small footer text must still be comfortably legible. Distinguish human decisions from model tasks and local memory processing with consistent shapes and a compact legend. Clear arrows, no crisscrossing, never imply that an AI suggestion automatically becomes accepted history. Do not render these art-direction instructions.

PALETTE: deep ink background, parchment typography and panels, brass rules and human-decision accents. Same editorial series, grid, type system and visual language as the Narrative / Passive companion, with the palette reversed. Five vertically organized areas: title, ordinary turn loop, memory architecture, active team, compact footer. The MEMORY area is the visual centerpiece.

VISIBLE TEXT AND LAYOUT:

HEADER:
"PROSPERO’S STUDY"
"Roleplay / Active"
"You inhabit a character. The world answers your move."
Small edition label: "v0.7.5 • Agent & memory guide"

A. Main loop, five clear steps with arrows:
"You act or speak" → "Memory packet" → "Primary prose" → "Review reply" → "Keep → next turn"
Small caption: "Your submitted text is saved. Generated replies wait for Keep."
Prominent slim agency callout:
"Your character’s choices and inner life remain yours."
"Shared agency is a separate, explicit option."
Tiny writer behavior caption: "Respond to the latest move; stop when the next meaningful choice is yours."

B. Large central section: "The same long memory, on this telling"
Show a saved archive feeding a smaller bounded context packet. Return arrow from Keep feeds the accepted path.
Archive/source cards:
"Accepted path" / "This branch’s permitted past"
"Canon & characters" / "Story-pinned versions"
"Plans & commitments" / "Separate from completed events"

Bounded packet:
"Context that fits"
"Recent prose + relevant originals"
"Required references + plans"
Small local-processing badge: "Local keyword recall • no extra model call"

Clearly marked optional rail feeding Author-view packet:
"OPTIONAL AUTHOR-VIEW RECALL"
"Prewriting search • Semantic search"
"Tentative relationship links • Reviewed summaries"
Caption: "Choose Long story. Extra recall aids start off."

Separate character-lens fork, clearly an alternative to Author view, NOT a default stage:
"Optional character lens"
"Uses recorded permitted evidence"
"Skips extra prewriting search"
Scope caption: "Author view is the default, including in Roleplay."
Small receipt card at packet exit: "Draft receipt: exact inputs, sources, coverage and fallback"

C. Team section: "A lean turn-by-turn team"
Four crisp compact cards:
"Primary prose" / "Narrates the world and cast"
"Collaborator" / "Discusses and retrieves without advancing history"
"Scene planner" / "Optional private drives and hooks; possibilities, not events"
"Scribe" / "Summaries, beat assessment and Canon aids"
A small support note: "Library assistant: proposes reference edits."
A distinct subdued shelf:
"START OFF IN THE ACTIVE TEMPLATE"
"Scene drafting • Dialogue • Readers • Triage • Revision patch"
"Enable the full scene workflow when wanted."

Small after-acceptance loop linked to archive:
"After accepted prose"
"Local indexes can warm without model calls."
"Optional automatic summaries and links require verified interruption and yield to writing."

D. Compact footer with three short guardrails:
"Each branch keeps its own accepted history."
"A claim is not proof; a plan is not an outcome."
"Knowledge guidance helps; the writer can still make continuity errors."
Final small caption:
"Templates are editable. Workspace switches still apply."
Legend: "Human choice • Model task • Local memory"
