"""Freeze unseen continuity checks and unchanged manuscript continuation inputs.

Author-written contrasts are diagnostic, not an estimate of error prevalence.
Review notes stay outside model payloads. Existing run artifacts are read-only.
"""
import argparse
import json
from pathlib import Path

from scripts.narrative_draft_check import PROMPT
from scripts.narrative_reliability import fingerprint, load
from server.database import encode
from server.memory.budget import token_estimate

CONTRASTS = [
    ('signed_receipt',
     'Yara sent a lens to Dev through the ferry office. Dev signed the receipt and locked the lens in his cabinet. Yara has received no message about its arrival. Dev and Yara now meet at the office.',
     'Dev stared at the receipt he had signed. "I am still waiting for the lens," he told Yara. "Nobody delivered it." He began to fill out a missing-cargo form.',
     '"Did the lens reach you?" Yara asked. Dev nodded. "I signed for it. It is in my cabinet." She pulled out the invoice and asked about the hire charge.',
     'Recipient denies the recorded receipt; sender can learn of it through new dialogue.'),
    ('unsent_message',
     'Asha promised to warn Bram if the sluice failed. She wrote a warning but left it unsent in her pocket. Nobody else carried word to Bram. The two now meet beside the sluice.',
     '"You received my warning yesterday," Asha said. Bram recalled reading it over breakfast. The paper had prepared him for the broken sluice.',
     'Asha took the unsent warning from her pocket. "I should have brought this sooner." Bram unfolded it and read, his expression tightening.',
     'No retrospective sending or receipt; a new handoff and new knowledge are allowed.'),
    ('hidden_sale',
     'While Leif and Esme were away, the owner sold the millstone to a distant farm. Neither witnessed the sale or received a report. They returned to a locked mill with its windows shuttered.',
     'Esme knocked once. "The owner sold the stone to a farm," Leif said. He knew there was no point waiting, so they turned away.',
     'Esme knocked once. "No answer," she said. Leif looked at the shutters. "Perhaps he has gone out. Let us ask at the inn." Beyond their knowledge, the sold stone was already on the farm road.',
     'Narrator may retain sale; characters cannot use hidden sale to decide.'),
    ('released_work',
     'Mali offered to mend Odo\'s sail before Monday. Later she withdrew the offer because her wrist was injured. Odo explicitly released her from the promise and arranged to do his own repairs. They meet again on Sunday.',
     'Mali remembered the promise. "You still owe me the repairs by tomorrow," Odo insisted, treating their agreement as binding. She bowed her head and accepted that the old obligation remained.',
     'Mali remembered the promise she had made. Her wrist still ached. "How are your repairs going?" Odo asked her to hold a corner of the sail while he showed her his uneven stitch.',
     'Withdrawal ends obligation; remembering it and new voluntary assistance do not revive it.'),
    ('rival_accounts',
     'In Tavi\'s hearing, Ren said the bell rang at midnight; Pella said it rang an hour later. Neither supplied a witness. The broken clock could settle nothing. Tavi meets Ren and Pella again. The narration has not established the hour.',
     'Tavi set aside the broken clock. Pella was lying: the bell had certainly rung at midnight. Ren smiled, relieved that the truth was finally settled.',
     '"Ren says midnight; Pella says one," Tavi said. "The clock cannot choose for us." Pella suggested asking the watchman. Ren agreed to go with her.',
     'Keep competing claims attributed; a new investigation does not settle them.'),
    ('earlier_checkpoint',
     'Kemi promised to bring a brass key to Noll. The current path ends as Noll opens his door to her. The supplied history records no custody, dispatch or handoff after the promise.',
     'Kemi remembered giving the key to a porter that morning. "He must have lost it," she said. Noll remembered seeing the porter leave and nodded in agreement.',
     '"The key?" Noll asked. Kemi paused on the threshold. His hand remained on the open door while he waited for an answer.',
     'No invented retrospective explanation or witness; unresolved history may remain unresolved.'),
]


def freeze(artifacts, destination):
    rows = []
    for name, history, flawed, control, note in CONTRASTS:
        context = {'history': [{'role': 'narrator', 'text': history}], 'direction': 'Continue this conversation.'}
        for variant, draft in [('flawed', flawed), ('control', control)]:
            rows.append({'id': f'holdout/{name}/{variant}', 'payload': {'context': context, 'draft': draft},
                         'expected': 'concern' if variant == 'flawed' else 'control', 'review_note': note})
    run = artifacts / 'manuscript-trajectory-live-01'
    requests = load(run / 'requests.json')
    report = load(run / 'report.json')
    writers = [r for r in requests if r['kind'] == 'writer']
    assert len(writers) == len(report['steps']) == 8
    for step, request in zip(report['steps'], writers, strict=True):
        assert step['output'] == request['output']
        rows.append({'id': f'manuscript/{step["path"]}/{step["step"]}',
                     'payload': {'context': json.loads(request['content']), 'draft': request['output']},
                     'expected': 'unscored', 'review_note': 'Review original source and draft; do not assume all prose is faulty.',
                     'origin_report_sha256': fingerprint(run / 'report.json')})
    # Preserve complete manuscript evidence. Account for review overhead explicitly;
    # never trim sources to make an apparently cleaner continuity result.
    maximum = max(token_estimate(PROMPT, r['payload']) + 128 for r in rows)
    manifest = {'format': 'prospero-draft-check/1', 'prompt': PROMPT, 'cases': rows,
                'context_tokens': 10240, 'max_output_tokens': 512, 'temperature': 0,
                'maximum_estimated_input_tokens': maximum,
                'method': 'Six unseen authored flawed/control contrasts and eight exact manuscript continuations. One check per draft; labels withheld. Review receives full original evidence plus draft, with a separately declared 10240-token allowance.'}
    assert maximum <= manifest['context_tokens'] - manifest['max_output_tokens']
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    (destination / 'manifest.sha256').write_text(fingerprint(destination / 'manifest.json'), encoding='ascii')
    print(f'Frozen {len(rows)} checks; maximum estimated input {maximum}. No provider calls.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    args = parser.parse_args()
    freeze(args.artifacts, args.fixture)
