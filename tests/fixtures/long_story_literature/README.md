# Frozen literature retrieval challenge

The original Project Gutenberg downloads, including their license notices, are retained unchanged. `sources.json` records their URLs, retrieval time, byte lengths and SHA-256 hashes. The catalogues identify these editions as public domain in the United States. No inference about other jurisdictions is made here.

- Arthur Conan Doyle, *The Adventure of the Speckled Band*, selected from [The Adventures of Sherlock Holmes, #1661](https://www.gutenberg.org/ebooks/1661).
- Henrik Ibsen, *A Doll's House*, translated by R. Farquharson Sharp, [#2542](https://www.gutenberg.org/ebooks/2542).
- E. M. Forster, *The Machine Stops*, selected from [The Eternal Moment and Other Stories, #72890](https://www.gutenberg.org/ebooks/72890).
- Jack London, *To Build a Fire*, selected from [Lost Face, #2429](https://www.gutenberg.org/ebooks/2429).

For reproducible working offsets, the loader removes the UTF-8 BOM and normalizes CRLF/CR to LF. It does not alter the stored downloads. The anthology boundaries are pinned to these verified editions, so other stories and Gutenberg boilerplate are excluded from retrieval. The original story is partitioned into contiguous, paragraph-preferred passages of at most 2,400 characters. These are simulated accepted narrative messages, not genuine chat-turn boundaries.

`annotations.json` contains authoring-style queries, exact supporting text and rationales. Quotes match unique whitespace-normalized spans in the original working text. Each required evidence group accepts any of its declared alternative quotes; a multi-group question requires all groups. Annotation labels are never given to retrieval. Unknown questions have no asserted answer and are not counted as successful abstentions merely because a retriever returns nothing.

`freeze.json` pins annotations, source provenance, evaluator code and production retrieval code before the first scored run. Freeze creation is explicit, refuses to replace an existing freeze, and evaluation refuses changed inputs. A future correction needs a new version with its rationale and both results retained. Do not adjust labels, queries, scorer parameters or ranking to improve this version's results after seeing them.

These annotations were authored by the implementation assistant after inspecting source passages, without looking at this corpus's retrieval scores. They have not been independently adjudicated by a person and are not an independently collected user-manuscript holdout. Their expected spans may omit other adequate evidence. This small, English-only published-literature suite does not establish general narrative understanding, role-boundary correctness, answer quality, multilingual quality or statistical superiority. It supplements the synthetic development/regression suite; it does not replace provider-backed writing evaluation.
