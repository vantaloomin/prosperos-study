GROUPS = [
    ('Interactive writing', ['writer']),
    ('Scene planning', ['scene-plan']),
    ('Scene drafting', ['scene-draft', 'scene-dialogue']),
    ('Independent review', ['review-blind', 'review-informed']),
    ('Revision', ['scene-triage', 'scene-patch']),
    ('Scribe', ['scribe']),
    ('Alongside your writing', ['collaborator']),
    ('Library assistance', ['library-assist']),
]
FLOW = {key: {'group': group, 'order': index} for index, (group, key) in enumerate(
    (group, key) for group, keys in GROUPS for key in keys)}
NOTES = {
    'scene-plan': 'Plans scene options, beats and private background. Each task keeps its own evidence and choices.',
    'review-blind': 'Reads prose through selected lenses without seeing Canon, rules, rolls or other reports.',
    'review-informed': 'Checks rules, continuity and approved beat coverage against the supplied primary sources.',
    'scribe': 'Proposes continuity, memory summaries and Canon search aids; prepares optional beat assessment after acceptance.',
    'library-assist': 'Drafts, critiques or tightens one Library field. Applying or publishing a suggestion remains your choice.',
    'memory-summary': 'Summarizes accepted prose with exact quotations. Supports explicit batches and opt-in maintenance; saving still requires review.',
    'authoring-enrich': 'Suggests summaries, topics and aliases for selected Canon excerpts. Applying them requires review; original prose stays intact.',
    'writer': 'Drafts the next passage. When disabled, write in the composer yourself.',
    'beat-assessment': 'Checks whether a completed beat calls for optional chance. Skipped when disabled.',
    'scene-options': 'Proposes different approaches to the scene. Skip to work directly from your direction.',
    'scene-beats': 'Turns the chosen direction into a beat plan. Skipping it also skips beat coverage.',
    'scene-brief': 'Extracts continuity for the plan. Full source context remains available if skipped.',
    'scene-draft': 'Writes the proposed scene. Disable it to use manual writing instead.',
    'scene-dialogue': 'Fills dialogue slots. When disabled, the scene writer includes dialogue in its prose.',
    'scene-coverage': 'Checks the draft against its beats. A skipped check is never reported as passed.',
    'scene-triage': 'Organizes review findings into a revision proposal.',
    'scene-verify': 'Rechecks disputed findings before a revision decision.',
    'scene-patch': 'Applies approved prose changes to a draft.',
    'scene-dialogue-patch': 'Applies approved dialogue changes when dialogue is split.',
    'scene-patch-check': 'Checks changed passages. Skipped checks remain visible at acceptance.',
    'scene-continuity': 'Proposes new continuity entries and a scene summary. Skipping preserves existing memory.',
    'collaborator': 'Chats beside the story without advancing it. Invoked only when you ask.',
    'background-interpretation': 'Interprets prepared private background. Invoked only when requested.',
}


def flow_metadata(key):
    return {**FLOW.get(key, {'group': 'Other', 'order': 999}),
            'description': NOTES.get(key, 'Runs only when selected for this workflow; disabling it skips new requests.')}
