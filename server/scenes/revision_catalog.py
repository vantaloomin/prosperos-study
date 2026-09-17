REVISION_STEPS = [
    {'key': 'scene-triage', 'name': 'Review triage', 'scope': 'selected independent reports and frozen draft'},
    {'key': 'scene-verify', 'name': 'Disputed claim verification', 'scope': 'one triage item and frozen sources'},
]
REVISION_KEYS = [step['key'] for step in REVISION_STEPS]
REVISION_PROMPTS = {
    'scene-triage': '''Read every supplied finding and propose an accountable revision plan. Reports are
claims, not authority. Merge overlapping findings by passage, preserving every finding ID exactly once;
explain disagreements. Respect this Story's genre, rules and player agency, without fixed stylistic bans.
Return {"summary":"assessment and limits","approach":"patch","items":[{"id":"t1",
"finding_ids":["r1f1"],"disposition":"verify","reason":"why","action":"concrete proposed edit or empty",
"evidence":[{"source_id":"exact supplied ID","quote":"verbatim source excerpt"}]}]}.
Use disposition hard-fix for a confirmed hard violation, fix for an accepted suggestion, cut for a cut,
overrule for a misreading with exact evidence, verify for a disputed claim requiring verification, or
hold for a structural decision such as changed knowledge, ending, thread or player agency. Do not downgrade
a hard finding into fix or cut. Fixes, cuts and holds need a concrete action; overrule needs exact evidence.
No findings is a valid empty items list. Recommend approach redraft when local edits cannot preserve the
approved beats or when accumulated violations require rewriting. Otherwise use patch. Do not rewrite prose,
approve a package, invent evidence, or claim changes were applied. User approval is still required.''',
    'scene-verify': '''Verify the single supplied disputed triage item against the frozen primary sources.
Reviewer claims and the proposed draft are not evidence that a fact was established in accepted history.
Distinguish established facts, user constraints, proposed developments and interpretation. Do not invent
external research or treat absence of evidence as proof. If the supplied material cannot settle the claim,
return undecidable and explain what information is missing. Do not rewrite the scene or change Story state.
Return {"summary":"verdict with reasoning and limits","verdict":"confirmed",
"evidence":[{"source_id":"exact supplied ID","quote":"verbatim excerpt"}],"smallest_fix":"proposal or empty"}.
Verdict is confirmed, rejected or undecidable. Confirmed/rejected require exact source evidence. Your
verdict is advice: the director must resolve the finding and explicitly approve any resulting change.''',
}
