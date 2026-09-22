# v0.8.0 representative output evaluation

On 2026-09-20, five short writing tasks exercised a real local model through the application. They eventually produced two contrasting style revisions, a complete draft/readers/revision recipe, a scoped Companion shortening proposal, and sample-analysis suggestions. These are observed examples, not a quality benchmark: the model added details, missed an instruction, and needed explicit retries. None of these proposals was applied to the author's workspace.

## Model and method

LM Studio's local OpenAI-compatible endpoint, `http://127.0.0.1:1234/v1`, was reachable. Its already loaded model was **`ateron_gemma-4-novelist-eclipse-31b`**; the advertised loaded context was 65,024 tokens. The disposable application profile used a 16,000-token context allowance, temperature 0.5, a 180-second timeout and initially a 3,000-token maximum output. Other sampling and reasoning controls retained provider defaults. One new full-recipe run explicitly used a separate 6,000-token-output profile after the original request reached its limit. The original request retained 3,000.

The user's database was inspected read-only to locate the configured local endpoint. All requests, profiles, invented text, styles, recipes, proposals and analysis records were created in a separate disposable database. No cloud provider was called. Each stage was started explicitly through the application API; retries reused its recorded inputs. The model's raw output, reported usage and application result were retained separately.

There were **15 real inference calls**, totaling **558.468 seconds** of measured call time (8.812–70.172 seconds per call). Provider-reported totals were **33,493 input tokens**, **25,398 output tokens**, including **22,536 reasoning tokens** and **2,862 response tokens**. These totals include failed attempts. They are not estimates of author workflow time or billing; cost was not reported.

## Inputs

Every prose case began with this invented passage:

> Mara put the unopened letter on the kitchen table. Rain tapped the window. Jon stood beside the kettle, his hand on its handle. "I am not opening it." Mara watched a drop run down the glass. Jon took his hand away from the kettle. Neither of them moved the letter.

The recipe asked for 70–110 words, both named speakers, the unopened letter, rain outside, the exact spoken sentence, and an ending without deciding to open the letter. It prohibited invented offstage events or motives. The two style choices were:

- **Restrained observation:** concrete verbs and ordinary nouns; no metaphors or explicit emotional explanation; third-person external observation; past tense; unchanged dialogue; mostly short sentences with a quiet closing pause. Avoid “suddenly,” “somehow,” “a testament,” and “a dance of.” Its example was “The kettle clicked off. She left the cup where it was. Across the table, he folded the receipt once.”
- **Flowing observation:** longer, linked sentences and sensory detail grounded in visible actions; the same viewpoint, tense and dialogue constraints; varied sentence lengths with a short ending. Its additional instruction prohibited explaining hidden feelings or inventing additional events. It supplied no example.

The full recipe used the restrained style for drafting and revision, with an independent dialogue reader and an informed continuity reader between them. Readers received their existing separate source scopes. The Companion request was: “Shorten this to 35-45 words. Keep Mara, Jon, the unopened letter, the rain, and the spoken words exactly. Leave the letter unopened. Do not explain what they feel.” It targeted the complete composer passage and requested a proposal.

Sample analysis used only the restrained example above and a second selected sample: “He set the key beside her plate. She turned the plate a little. The key stayed where it was.” Complete rendered instructions, source indexes, serialized request content and model profiles are preserved in the evidence files below.

## Attempts and interventions

| Phase | Calls | Observed outcome |
| --- | ---: | --- |
| Initial five cases | 5 | All returned complete JSON inside one enclosing Markdown code block. The three new parsers rejected that wrapper. Original output and errors remained inspectable. |
| Explicit original-input retries after parser fix | 5 | Both style revisions, Companion shortening and analysis completed. The full recipe's first writer reached 3,000 output tokens (2,937 reasoning, 63 response), so incomplete output was refused and no next stage began. All five retries retained exact original request inputs. |
| New full recipe, 6,000 maximum output | 3 | Draft and independent reader completed. The informed reader included an empty `coverage` list even though its instructions required omitting coverage without approved beats. The schema rejected it; the run stopped for attention. |
| One explicit reader retry and final revision | 2 | The same frozen informed-reader request produced a valid report. Explicitly starting revision completed the recipe and created a pending proposal. |

The compatibility fix accepts exactly one whole JSON or unlabeled code block around a response. It retains original provider bytes and does not loosen source, authority, completion or result-schema checks. Commentary around a block, multiple blocks, non-JSON fences, partial JSON, extra authority fields and foreign or duplicate source references remain refused. Thirteen expanded parser/lifecycle/archive checks passed after this change (`test-results/v080-structured-02.log`); an earlier overlapping integration run passed 82 checks (`v080-structured-01.log`). No semantic exception was added for the invalid reader report.

## Output review and author corrections

Word counts below use whitespace-separated words in the saved replacement, not the model's own estimate.

| Case | Final observed result | Required review or correction |
| --- | --- | --- |
| Restrained style | 79 words; short sentences, external actions, original quoted sentence, both characters, rain and unopened letter. | Adds materials/colors and Jon stepping back. These remain visible actions, but require removal if the author intends exact event/detail preservation. |
| Flowing style | 89 words; longer connected sentences, sensory description and a short final sentence. Required names, quoted sentence and unopened letter remain. | Adds kettle steam, shadows and Jon stepping back. The extra action conflicts with the style's explicit prohibition on additional events; remove it and review the invented details. |
| Full draft/readers/revision recipe | Final proposal is 71 words. Both reader reports have no findings. Revision retains the dialogue, letter, rain and external viewpoint. | Adds Jon looking between the letter and Mara, stepping back, and a wooden table. The recipe prohibits offstage events/motives rather than all new visible action, but these additions still need author judgment. The readers' clean reports do not establish fidelity to every original detail. Revision changes little from the draft. |
| Companion shortening | 41 words, within 35–45; retains both names, unopened letter, rain and exact spoken sentence without explaining feelings. | No correction identified against the stated brief. It omits the hand-withdrawal action; retain or restore that detail if the author considers it essential. |
| Selected-sample analysis | Five editable suggestions: prose, viewpoint, tense, rhythm and description. Each cites exact text from a selected sample. | The observations fit these two brief examples. They are insufficient to infer an author's general style. Dialogue conventions and unwanted habits were not invented from absent evidence. Publication remains an author action. |

The successful Companion output was:

> Mara put the unopened letter on the table. Rain tapped the window. Jon stood by the kettle, his hand on the handle. "I am not opening it." Mara watched a drop run down the glass. Neither of them moved the letter.

The final multi-stage proposal was:

> Mara set the unopened letter on the wooden kitchen table. Rain tapped against the window glass. Jon stood beside the kettle, his hand gripping the handle. He looked at the envelope and then at Mara. "I am not opening it." Mara watched a single drop of water run down the pane. Jon released his hold on the kettle and stepped back from the counter. Neither of them moved toward the letter.

## Evidence and limits

Raw reports and executable evaluation harnesses are retained under `C:\Users\Jim\.codex\visualizations\2026\09\20\01a0bc1f-bec5-7371-bb67-cf3b48b43bda`:

- `v080-live-evaluation-result.json` and `v080-live-evaluation.py`: initial five calls and original target preservation.
- `v080-live-recovery-result.json` and `v080-live-recovery.py`: five exact-input retries and successful short outputs.
- `v080-live-full-recipe-result.json` and `v080-live-full-recipe.py`: explicit larger-output run and preserved original limit.
- `v080-live-reader-retry-result.json` and `v080-live-reader-retry.py`: one exact-input reader retry and final revision.

Corresponding process logs are `test-results/v080-live-evaluation-01.log`, `v080-live-recovery-01.log`, `v080-live-full-recipe-01.log` and `v080-live-reader-retry-01.log`. Endpoint discovery is recorded in `test-results/v080-live-availability-01.json`.

This evaluation covers one loaded local model, one invented short passage, two styles and two short samples. It does not establish universal style adherence, novel-length continuity, other providers' quality, determinism, or reliable reader detection. The deterministic acceptance/browser checks separately establish target scope, application, Undo, persistence, restart and archive behavior. Generated wording remains reviewable precisely because successful structured output does not guarantee a faithful revision.
