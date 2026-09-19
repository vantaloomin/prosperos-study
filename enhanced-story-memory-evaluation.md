# Enhanced Story memory evaluation — 2026-09-19

The live ordinary-writing comparison supplied **19/19 required permitted passages** with prewriting recall plus model-generated relationship links, versus **12/19** for baseline and **17/19** for prewriting alone. The linked draft remembered the successful sibling's signed receipt, but other drafts still omitted events or invented unsupported history. Complete retrieval did not guarantee correct prose.

All five implementation stages are evaluated. The controlled comparison below isolates retrieval behavior; the subsequent live comparison measures actual model responses and reports their limitations separately.

## Controlled method

Run `.venv/Scripts/python.exe -m scripts.relationship_evaluation --output-directory <new-directory>` from the repository. The script creates disposable synthetic databases and a `report.json` containing exact inputs, source coverage, profiles, query receipts, annotation jobs and measured request timings. It calls the ordinary generation endpoint; drafts remain unaccepted. Correct queries and annotations come from a controlled provider, and writer output is a placeholder. No network requests or personal story data are used.

Each variant uses the same writer direction and model configuration: 4,096 context tokens, 512 reserved output tokens, and a **3,584-token input allowance**. The overhead margin also fits inside that allowance. Semantic search is disabled; the user-selected live writing model is not an embedding model. Long filler separates earlier events from the present scene. Sibling and earlier-fork cases use actual branches, and exclusion uses the author-decision API.

The measured artifact is `relationship-evaluation-01/report.json` in this task's visualization artifact directory. Each case has one sample per variant; these are acceptance fixtures, not a representative corpus or a statistical study.

| Case | Baseline | Prewriting | Prewriting + supplied links |
| --- | ---: | ---: | ---: |
| Promise → handoff → failed delivery | 2/3 | 3/3 | 3/3 |
| Successful-delivery sibling | 1/3 | 3/3 | 3/3 |
| Changed names and pronouns | 1/3 | 2/3 | 3/3 |
| Withdrawn promise | 2/4 | 4/4 | 4/4 |
| Conflicting testimony | 1/3 | 2/3 | 3/3 |
| Excluded handoff | 2/2 | 2/2 | 2/2 |
| Fork before the handoff | 1/1 | 1/1 | 1/1 |
| **Required passages supplied** | **10/19** | **17/19** | **19/19** |
| **Complete cases** | **2/7** | **5/7** | **7/7** |

All variants supplied zero forbidden passages. Every final packet fit its allowance. Accepted plan lists remained empty. These assertions do not grade whether prose respects testimony, knowledge or withdrawal: no narrative model ran.

## Controlled cost and interventions

Each baseline continuation used one controlled writer call. Each enhanced continuation used one controlled query call plus one controlled writer call. Preparing the initial links made four controlled annotation requests per case, including uninformative chunks when selected. There were 28 annotation calls, 14 query calls and 21 writer calls across the experiment, all simulated.

Each linked variant required one explicit batch-preparation action and zero link-curation actions after enabling its settings. This is the measured setup for these small fixtures, not a claim that a whole manuscript needs only one action. Automatic preparation is separate and requires a connection with verified interruption; OpenRouter has not met that requirement. No manual plan records or query edits were supplied through the author UI. The controlled provider itself was scripted with correct interpretations, which removes the central live-model uncertainty from this experiment.

Measured controlled pipeline time ranged from 0.068–0.106 seconds for baseline generation, 0.081–0.136 seconds for prewriting generation, and 0.085–0.128 seconds for linked generation. Initial four-request preparation took 0.099–0.204 seconds per case. These numbers include local API/database work with an immediate fake provider; they are not inference latency estimates or speedup claims.

## Live method and evidence

After the user relaunched LM Studio, the final comparison used the already-loaded `ateron_gemma-4-novelist-eclipse-31b` instance through the native API. All 63 responses reported that model. The disposable writer configuration used temperature 0, reasoning off, 4,096 context tokens, 512 maximum output tokens and the same **3,584-token input allowance**, including overhead. The loaded instance and saved personal profiles were not reconfigured. No embedding model was called.

Each of seven synthetic directed-prose stories used the neutral title **The parcel**, with accepted narrator passages. None of the outcome-labelled case identifiers appeared in any request content. The same direction requested a 120–180-word scene, the recipient's question and sender's answer, correct character knowledge, and unresolved missing or conflicting history. Each variant ran once in fixed order: baseline, prewriting, then prewriting with links prepared by the same model. This is a small acceptance comparison, not a representative corpus or statistical study.

The measured artifacts are `relationship-live-lmstudio-03/report.json`, `requests.json`, and `narrative-review.md` under this task's visualization directory. The review records hashes of the unchanged raw artifacts. It examines all 21 drafts against source history and final inputs, with variant identities visible, by the implementation agent; it is not blind or independently human-graded. Raw numeric narrative scores remain null, rather than inventing a quality metric after observing results.

| Case | Baseline | Prewriting | Prewriting + live links |
| --- | ---: | ---: | ---: |
| Promise → handoff → failed delivery | 2/3 | 3/3 | 3/3 |
| Successful-delivery sibling | 2/3 | 3/3 | 3/3 |
| Changed names and pronouns | 1/3 | 2/3 | 3/3 |
| Withdrawn promise | 3/4 | 4/4 | 4/4 |
| Conflicting testimony | 1/3 | 2/3 | 3/3 |
| Excluded handoff | 2/2 | 2/2 | 2/2 |
| Fork before the handoff | 1/1 | 1/1 | 1/1 |
| **Required passages supplied** | **12/19** | **17/19** | **19/19** |
| **Complete cases** | **2/7** | **5/7** | **7/7** |

Every final input fit its allowance. No excluded or sibling-only original appeared in any of the 21 packets, and accepted plan lists remained empty. These are input and accepted-state checks; they do not assert that the model never invents the excluded event in its output.

All **14 query preparations completed**. Of **28 annotation responses**, **27 passed validation**, yielding **29 annotation items**. The rejected changed-name response supplied empty `relation` values outside the permitted schema. It was not retried, and the validator was not relaxed. Later valid annotations still linked all required originals for that case. Grounded quotations establish source provenance, not interpretive truth.

## Live prose review

| Case | Observed result |
| --- | --- |
| Failed delivery | Prewriting and linked drafts recount the handoff and keep ravine loss in narrator knowledge. Baseline lacks the handoff. |
| Successful sibling | Linked prose remembers Ilan receiving the parcel and signing for Tess. Baseline invents disappearance; prewriting still treats delivery as pending despite receiving the successful-delivery evidence. Linked prose also overstates Sera's knowledge of fulfillment. |
| Names/pronouns | Linked prose recovers Tess's handoff and Maren's identity but omits cliff loss. Prewriting assigns Maren personal memory of the accident without support. |
| Withdrawal | All variants respect the accepted withdrawal. Linked prose also retains handoff and narrator-only loss. |
| Conflicting testimony | Linked prose retains uncertainty and the handoff, but omits Tess's explicit claim that delivery happened. Complete evidence is only partly used. |
| Excluded handoff | All variants invent some sending/transfer history; linked prose explicitly invents Sera entrusting Tess. The excluded original was absent from supplied evidence. Correct exclusion does not prevent unsupported model inference. |
| Earlier fork | Baseline and prewriting leave history unresolved. Linked prose invents a concluded journey and Sera knowing what happened. This sample regresses despite correctly scoped inputs. |

The measured gain is evidence availability. Narrative use is mixed; these samples do not establish an overall narrative-quality advantage or reliable knowledge-boundary compliance.

## Live cost and interventions

The final comparison made **63 inference calls**: 28 annotation, 14 query and 21 writer calls, with **121,706 provider-reported input tokens** and **7,742 output tokens**. It used seven explicit batch-preparation actions, zero link-curation actions, zero manual query edits and zero retries. It did not exercise live automatic background preparation or accept any generated draft. Whole-manuscript preparation cost remains unmeasured.

| Operation | Median seconds | Range seconds |
| --- | ---: | ---: |
| Baseline continuation | 6.217 | 5.791–6.285 |
| Prewriting + continuation | 8.822 | 8.435–9.496 |
| Prewriting with existing links + continuation | 8.861 | 8.330–9.226 |
| Initial four-request link preparation | 19.219 | 9.407–21.485 |

Continuation timings include local API/database work; initial link preparation is separate. Individual annotation request durations include scheduler waits and overlap, so summing them is not a wall-time measurement. Fixed ordering and provider caching can affect these values. They are observations on this instance, not throughput or speedup claims.

## Exploratory runs and compatibility fixes

The earlier OpenRouter `z-ai/glm-5.3-flash` probe returned HTTP 401 after 0.656 seconds and produced no output. It was not retried; the user's later LM Studio authorization enabled the comparison above.

LM Studio run 01 made 18 requests. It exposed JSON code fences and original-source aliases that strict parsing rejected, and a roleplay fixture that elicited only a question. Preparation now accepts one outer JSON fence and resolves a supplied original-source/node ID only when it identifies exactly one supplied chunk. Canonical chunk IDs, exact unique quotation spans and all existing bounds remain required. Ambiguous aliases and invalid schema values still fail; completed or fallback receipts remain frozen.

Run 02 made 63 requests after those fixes with directed prose, but its Story titles exposed case outcomes. Its prose is excluded from the final comparison. Run 03 above removes those labels and makes 63 requests. Total LM Studio inference calls across all three runs: **144**. No personal prose was sent and no saved personal profile was changed.

## Reproduction and remaining limits

Run `scripts/relationship_live_evaluation.py` as a module with `--execute-live`, a new `--output-directory`, and either `--lmstudio-model <already-loaded-instance-id>` or `--openrouter-profile-id <id>`. The LM Studio runner checks the loaded instance, available context and reasoning option before every request; it does not load or unload models. OpenRouter reads the selected profile's latest credential reference through read-only SQLite and restricts inference to `z-ai/glm-5.3-flash`. Both use disposable synthetic databases, bounded request counts and credential-free journals. Authentication, access and rate-limit failures stop further dispatch.

The default evaluates failed delivery and its successful sibling, with at most 18 calls. Pass `--cases failed_delivery successful_sibling changed_names_pronouns withdrawn_promise conflicting_testimony excluded_handoff fork_before_handoff` for the full 63-call comparison. A `stop-after-case` file in the output directory requests a stop between cases.

Live semantic quality, manuscript-scale storage/latency, automatic preparation on this model and repeated-sample narrative error rates remain unmeasured. Controlled tests establish their implemented contracts where applicable; they do not substitute for those measurements.
