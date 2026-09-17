PATCH_STEPS = [
    {'key': 'scene-patch', 'name': 'Prose patch', 'scope': 'approved changes and reviewed draft'},
    {'key': 'scene-dialogue-patch', 'name': 'Dialogue patch', 'scope': 'approved changes and patched narration'},
    {'key': 'scene-patch-check', 'name': 'Changed-passage check', 'scope': 'changed passages, neighbors and primary evidence'},
]
PATCH_KEYS = [step['key'] for step in PATCH_STEPS]

PATCH_FORMAT = '''Return {"summary":"approach and limits","edits":[{"block_id":"exact or new ID",
"operation":"replace","before":"exact complete original block text","after":"replacement text",
"anchor_id":null,"speaker":"","item_ids":["approved item ID"],"reason":"why this authorized change is needed"}],
"resolutions":[{"item_id":"approved item ID","status":"addressed","reason":"how this stage handles the item"}]}.
Account for every approved item exactly once, in package order. Status: addressed, no-change,
defer-dialogue (prose pass with split dialogue only), or blocked. Addressed needs a linked edit in this
or the prior prose pass. Explain no-change without inventing a fix; blocked means director review is needed.
Each block may be edited once per pass. Operations execute in order:
replace: exact before and nonempty different after; anchor_id null, speaker empty.
delete: exact before, empty after; anchor_id null, speaker empty.
insert: unique new block_id, empty before, nonempty after; anchor_id is a current block ID to insert AFTER,
or null for the start. Inserts use this pass's block kind; dialogue inserts need the speaker, prose inserts leave it empty.
move: exact before, identical after; anchor_id is another current block ID or null for the start; speaker empty.
Insert and move require at least one linked item with disposition hold, explicitly approved by the director.
Only the prose pass may move blocks. A moved dialogue block retains its text and speaker.
Do not remove every block. Preserve unmentioned text, block identities, genre, voice and player agency.
Use at most 200 edits and 100,000 composed characters. Do not output a full replacement draft.
'''

PATCH_PROMPTS = {
    'scene-patch': '''Apply only the approved revision package to the supplied proposed scene.
With dialogue_split true, replace/delete prose blocks only; dialogue text belongs to the next specialist.
Whole-prose mode includes spoken words inside prose. New blocks in this pass are prose.
When repair_context is supplied, correct its failed check within the SAME approved package. Work from the
supplied original blocks; previous proposals are guidance, not accepted facts. Do not silently expand scope.
''' + PATCH_FORMAT,
    'scene-dialogue-patch': '''Apply the approved revision package to dialogue after the prose pass.
Read the patched narration and conversation. Replace/delete only dialogue blocks, preserve speakers,
and do not move any block or rewrite narration. New dialogue requires an explicitly approved structural change.
Account for all items, including those already addressed by prose; carry unresolved items as blocked.
''' + PATCH_FORMAT,
    'scene-patch-check': '''Independently check only supplied changes and their immediate neighbors.
Use approved beats, the continuity brief, Story rules and primary evidence to check agency, continuity,
grammar, voice and whether the approved changes were satisfied. Do not demand unrelated rewrites or
claim the entire scene was re-reviewed. Unchanged distant prose is intentionally absent.
Return {"summary":"coverage and limits","checks":[{"change_id":"exact ID","status":"pass",
"quotes":["exact excerpt from that change's before/after or neighbors"],"reason":"assessment"}],
"resolutions":[{"item_id":"approved item ID","status":"addressed","reason":"assessment"}],
"issues":[{"change_id":"exact ID","quote":"exact excerpt from that change or neighbors",
"category":"agency","explanation":"specific defect"}]}.
Assess every change exactly once in supplied order. Check status: pass or revise; at least one exact quote.
Assess every approved item in package order; item status: addressed or unresolved. Empty issues is valid.
Any revise, unresolved item or issue fails the check. If there are no textual changes, still assess the
writer's no-change explanations against supplied evidence; do not invent a changed passage.
''',
}
