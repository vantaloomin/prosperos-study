"""Predeclared development intervention and prose-review rubric, not a runtime prompt."""

EVIDENCE_GUIDANCE = """Use the supplied evidence to constrain the story's past before drafting its next moment.
Distinguish a promise, an attempted action, a transfer and a completed outcome: none proves the next.
An explicit later outcome or accepted withdrawal still governs even if the current scene suggests a different expectation.
Treat dialogue and beliefs as attributed accounts; contradictory unverified accounts remain unresolved.
For each character, distinguish what they did, witnessed or were told from what only narration establishes.
Do not invent a memory, private certainty, confession, earlier handoff, loss or delivery to explain a gap in the supplied history.
Missing evidence establishes neither that an event occurred nor that it did not occur. Let characters remain uncertain;
do not turn uncertainty into a secret the narrator claims they possess. A search link is not evidence of an event or knowledge.
Relevant established outcomes must govern the scene; you need not recap every passage or force exposition.
You may invent new on-page actions and sensory detail consistent with the direction, without inventing their past causes.
Return natural story prose only; do not display this check, source IDs, a checklist or analysis."""

RUBRIC = {
    'outcome': 'Does prose contradict a supplied established outcome or accepted withdrawal?',
    'past_event': 'Does prose invent a retrospective event, transfer, loss or resolution to bridge missing history?',
    'knowledge': 'Does prose assert unsupported character witness, memory or private certainty?',
    'testimony': 'Does prose convert an unverified account into fact or silently resolve conflicting accounts?',
    'causal_use': 'Do relevant established relationships govern the scene without requiring a recap of every source?',
    'usability': 'Does usable fiction follow the direction without turning into diagnostic commentary or frozen inaction?',
}

CASE_NOTES = {
    'failed_delivery': 'Promise, transfer to Tess and loss are supplied. Loss is narrated; neither sender nor recipient is established as knowing its cause.',
    'successful_sibling': 'Ilan received the parcel and signed for Tess. Desk absence does not undo this. Sera is not established as knowing receipt occurred.',
    'changed_names_pronouns': 'Maren was called Sera; Tess is the male courier who lost the object. Do not give Maren a personal memory of the cliff accident.',
    'withdrawn_promise': 'Withdrawal and recipient acceptance end the obligation; they do not change whether handoff and loss happened.',
    'conflicting_testimony': 'Tess claims arrival, Ilan denies receipt, neither verified. Their testimony does not establish objective delivery or loss.',
    'excluded_handoff': 'Only promise and narrated courier loss are permitted. Do not assert how the courier obtained the object.',
    'fork_before_handoff': 'Only a promise is established before the current meeting. No journey, handoff, loss or private knowledge of an outcome is established.',
}
