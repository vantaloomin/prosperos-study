from server.authoring.catalog import AUTHORING_STEPS
from server.scenes.catalog import DRAFT_KEYS, PLAN_KEYS
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.revision_catalog import REVISION_KEYS
from server.workflow.catalog import REVIEW_ROLES

GROUPS = [
    ('Interactive writing', ['beat-assessment', 'writer']),
    ('Scene planning', ['background-interpretation', *PLAN_KEYS]),
    ('Scene drafting', DRAFT_KEYS),
    ('Independent review', [role['key'] for role in REVIEW_ROLES]),
    ('Revision', REVISION_KEYS + PATCH_KEYS),
    ('Continuity', CONTINUITY_KEYS),
    ('Story memory', ['memory-summary']),
    ('Alongside your writing', ['collaborator']),
    ('Library assistance', [step['key'] for step in AUTHORING_STEPS]),
]
FLOW = {key: {'group': group, 'order': index} for index, (group, key) in enumerate(
    (group, key) for group, keys in GROUPS for key in keys)}
NOTES = {
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
