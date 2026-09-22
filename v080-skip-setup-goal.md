# v0.8.0 goal: skip setup and start writing

Status: implementation complete on `codex/v0.8.0-personal-writing`, 2026-09-21. Implemented and verified. The subsequently authorized publication is covered by the [release notes](releases/v0.8.0.md); the implementation record below describes the state before publication.

## Objective

Let an author start writing without completing the six-step Story wizard. Add a visible **Skip setup** action beside Continue, explained by **Start now. You can change these settings later.** The guided setup remains available.

This is an approved addition to v0.8.0. Preserve the existing implementation and historical documentation. No commit, push, tag or publication is included.

## Required behavior

- [x] Show Skip setup on every unfinished wizard step before the final Start writing step, including the first step. Support keyboard access and narrow layouts.
- [x] Create the Story immediately, close setup, open the normal writing workspace and focus the composer. Do not insert an extra confirmation or final review step.
- [x] Preserve entered title, premise, opening, experience, writing preferences, model, Library versions and assistance choices. Use existing defaults for untouched choices; use **Untitled Story** only when the title is empty or whitespace.
- [x] Reuse the selected or configured primary writer when available. With no model, allow manual writing and make model setup available when AI assistance is wanted.
- [x] Do not automatically generate prose, invoke a model, roll chance or start a scene workflow. Preserve explicitly supplied opening text through the normal creation contract.
- [x] Keep all Story settings editable afterward through existing controls.
- [x] Retain existing validation for stale model/Library/opening references. Explain and preserve invalid choices rather than silently discarding them.
- [x] Share existing creation receipts and saved pending payloads. Duplicate activation must not create duplicate Stories; a lost response, close/reopen or reload must offer recovery of the exact saved request. Do not automatically resend on reload.
- [x] Preserve the guided Continue/Back/Start writing path and unfinished setup drafts.

## Scope and verification

Prefer the existing Story creation API, defaults and recovery mechanisms. Add only the frontend/default/focus changes needed for the approved flow; no database migration or new archive format is expected.

- [x] Verify shortcut payloads for empty and partially completed setup, model/no-model defaults, title fallback, source validation and frozen retry behavior using focused UI-model checks.
- [x] Run the existing onboarding backend checks to confirm atomic creation, no-model operation, no automatic work and receipt idempotency.
- [x] Exercise the rendered shortcut at desktop and narrow widths with reduced motion: fresh setup, entered choices, normal wizard, keyboard/composer focus, no-model manual writing, invalid references, duplicate activation and lost-response/reload recovery. Inspect screenshots and browser errors.
- [x] Run applicable UI-model tests, ESLint, TypeScript/build and whitespace checks. Use focused regression checks for this bounded addition; the earlier complete v0.8.0 suite remains a historical result rather than a claim about newly edited files.
- [x] Update the README and v0.8.0 release/change notes. Record actual verification, preserved work and remaining limitations here.

## Acceptance example

An author opens New Story, chooses Skip setup immediately and lands in the composer of Untitled Story. No model is required and no inference starts. A second author enters a title, premise and selected character, then skips the remaining steps; those choices and their pinned versions are retained. A simulated lost save response survives reload and one explicit retry opens the same Story without creating another.

Completion requires the implemented flow and passing applicable checks. Merely adding a button or writing this document does not complete the goal.

## Implementation record

The baseline is the completed v0.8.0 work in the existing feature branch. `NewStory.tsx` now presents Skip setup on steps 1–5 and uses the same atomic saved-request path as guided creation. `setup.ts` supplies the optional fallback title without weakening model, Library or greeting validation. `useStartWritingFocus.ts` waits for the dialog to close and the selected branch's composer to become ready, then focuses it once. The footer stays usable at narrow widths, with the explanation visible.

Verification passed: **113 UI-model tests**, **7 existing onboarding backend tests**, **24 rendered Chromium checks**, ESLint, TypeScript/production build and scoped whitespace checks. The backend tests reported two existing test-client deprecation warnings. The browser used Playwright because the Browser plugin was unavailable, at 1440×1000 and 390×844 with reduced motion. Desktop setup, narrow setup and the resulting narrow writing workspace screenshots were visually inspected. No unexpected browser errors or warnings occurred; one deliberately injected 503 exercised recovery.

The browser scenario verified keyboard activation, manual writing with no model, later title editing, selected writer/preferences/assistance and an old pinned Character edition, preserved invalid greeting choices, normal guided creation, Back and close/reopen draft persistence, duplicate-click protection and exact saved-payload recovery after reload. Changing the workspace's default writer before retry did not change the original request. Six disposable Stories were created with **zero provider calls** and no generation, scene, review, chance, Companion, recipe or style-analysis jobs.

The README, changelog, release notes and [validation audit](v080-validation.md#skip-setup-addition--2026-09-21) now document this addition and distinguish its focused checks from the earlier full-suite run. The 1,113-file baseline was compared after implementation: 1,102 files remained identical; eleven expected files changed and one focus hook was added. Earlier feature work and the four inherited historical documents remain intact. The disposable QA server was stopped. HEAD remains `515837613b67ec61087a771b9e6cb52e2f7de740`; nothing was committed or published.

Evidence is stored outside the repository at `C:\Users\Jim\.codex\visualizations\2026\09\20\01a0bc1f-bec5-7371-bb67-cf3b48b43bda`: `skip-setup-browser-result.json`, `skip-setup-final-check.json`, `skip-setup-models-02.log`, `skip-setup-backend-01.log`, `skip-setup-lint-02.log`, `skip-setup-build-03.log`, `skip-setup-browser-04.log`, `skip-setup-desktop.png`, `skip-setup-mobile.png` and `skip-setup-started-mobile.png`.

Limits: the full 1,756-test backend suite was not rerun for this bounded frontend addition. This verification does not cover other browser engines, a physical mobile keyboard or live model behavior. No backend or archive schema changes were needed.
