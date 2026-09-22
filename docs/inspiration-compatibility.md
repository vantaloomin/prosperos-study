# Inspiration decks: implementation contract

Status: weighted decks, the Library editor, preview/draw controls, collection review/export, starters, unsent-input handoff and private-archive recovery are implemented and verified in focused backend/browser checks. The completed whole-release gate is recorded in [v090-validation.md](https://github.com/vantaloomin/prosperos-study/blob/v0.9.0/v090-validation.md).

## Using decks

Open **Library → Inspiration** to create a deck or review a starter collection. Publish the card definitions before recording draws; the editor also offers a separate preview of unsaved changes. Use **Preview & draw** to inspect odds, require tags or exclude cards, then explicitly record a draw. Version history retains earlier cards and imported source downloads. Archive hides a deck from the default list; **Include archived decks** makes restoration available.

In a Story, **Inspiration** opens the same deliberate selection controls. Inspect or copy a recorded result, or choose **Add to unsent input** to append it to the existing unsent text. Sending that input is a separate author action. History shows 100 receipts at a time with navigation to earlier results. A lost response retains the frozen draw request on this browser so a retry returns its existing receipt.

**Export collection** selects explicit deck versions. **Import collection** stages a file for detailed review, with skip as the default for duplicate definitions. Explicit copies and version updates require the author's choices. If a publication response is lost, reload recovers the completed result using the saved operation; retry never silently becomes a second copy. A browser storage failure prevents submission and explains how to retry safely.

## Selection and history

A deck publishes immutable versions with a name, description, version note and 1–500 cards. Cards have a stable ID, title, literal text, up to 20 case-sensitive tags, a positive weight and an enabled flag. Editing a card keeps its ID; duplicating a whole deck creates a separate deck identity. Old versions remain available after edits or archiving.

Weights range from 0.000001 to 1,000,000 with at most six decimal places. Selection uses exact integer units (one million units per weight of 1), avoiding cumulative floating-point selection errors. Disabled cards, explicitly excluded IDs and cards missing any required tag are ineligible. A preview reports every card's reason, effective weight and exact numerator/denominator probability. Invalid exclusions and an empty eligible population are errors.

Every draw is **with replacement**. There is no depleted pile or implicit draw-without-replacement behavior. Preview uses a separate seeded SHA-256 rejection-sampling stream, supports 1–100 examples, and writes no draw, Story, chance or generation record. A deliberate draw uses the operating system's random source and saves the deck version, eligibility, ticket and chosen card. Retrying the same operation returns that recorded result; changed choices under the same operation ID are rejected.

Draws can be independent Library inspiration or associated with an explicitly selected Story path and its current revision. Association records the source head without changing the path. These manual inspiration draws do not enable or consume Story RNG, start model work, or declare Canon. Generation integration is limited to an author's deliberate use of the text in an unsent input; ordinary saved requests retain their frozen text.

## Portable collections

`prospero-inspiration-pack`, format version **1**, contains a name, description and 1–32 self-contained deck definitions. One source file is limited to **8 MiB**. A collection exports specifically selected versions; it contains no Story records, draw history, model profiles or private conversations. Known private connection metadata is omitted on export and rejected on import before staging. There are no supported external dependencies or executable actions.

Import first stages the exact UTF-8 source, including BOM/spacing, and previews every deck. Unknown envelope, deck, content and card fields remain inert, inspectable metadata; the original also preserves them exactly. Unsupported actions, depletion rules and dependency descriptions are never enabled. A reviewed import selects the desired deck keys and defaults to skipping equivalent card definitions, including matches against native authored versions and earlier items in the same collection. Display names do not determine identity. Explicit new copies and exact-target/current-version updates are available; a failure rolls back the whole selected import operation.

Three original starter collections offer quiet character moments, mystery complications and speculative encounters, five editable cards each. Reading or importing a starter draws nothing and enables nothing in a Story.

## Recovery

Private archive format **54** adds deck/version, draw and accepted pack-source/origin groups. Versions and receipts are validated together: eligible cards, probabilities and outcomes must agree with the recorded version and ticket. Restoring remaps live deck, version, branch and source links while keeping card IDs, source bytes, probabilities and outcomes unchanged.

Workspace archives include all decks and draw history. Story archives include draws associated with their selected Story's paths and the complete version histories of the referenced decks, plus accepted pack originals. Unpublished pack staging stays local. Earlier archive formats upgrade with empty deck groups; no draws or starter decks are invented during recovery.

Measured deck evidence, including exact odds, fresh-workspace collection/archive recovery, frozen generation input, 32 browser checks and inspected layouts, is recorded in [v090-validation.md](https://github.com/vantaloomin/prosperos-study/blob/v0.9.0/v090-validation.md). These are deterministic and simulated-provider checks, not measurements of live writing quality.
