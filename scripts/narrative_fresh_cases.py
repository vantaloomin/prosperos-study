"""New authored narrative probes, frozen before candidate outputs are inspected.

These short fixtures test transfer beyond the parcel regressions. They are not
the manuscript-scale corpus, and labels are not independent human adjudication.
"""
import argparse
import hashlib
from pathlib import Path

from scripts.narrative_reliability_contract import EVIDENCE_GUIDANCE, RUBRIC
from server.database import encode
from server.memory.budget import token_estimate
from server.memory.packet import GUIDANCE
from server.prompts import DEFAULT_WRITER

CASES = [
    {
        'case': 'depot_receipt',
        'passages': [
            'Ada promised to return the survey instrument to Beren before the north road closed. She delivered the sealed case to Fen at the depot, asking him to carry it on the afternoon cart. Fen wrote the destination on a luggage label while she watched. Ada left for the quarry before the cart departed. No word from Beren reached her there.',
            'At dusk Fen placed the sealed case in Beren\'s hands. Beren checked the instrument for damage, signed the delivery book and put the case in the locked cupboard beside his bed. Fen departed without sending Ada a message. Beren kept the key to the cupboard in his waistcoat.',
            'Two days later Ada came back from the quarry. She and Beren sat at a bare depot table to settle the hire charge. The case was still in Beren\'s locked cupboard at home. Ada had received no report of the delivery. The clerk laid a blank account sheet between them and went to fetch ink.',
        ],
        'direction': 'Write 120–180 words of third-person prose. Ada asks whether the instrument arrived; Beren answers and they begin settling the hire charge. Keep receipt, current location and each person\'s knowledge consistent. Beren may tell Ada what she did not previously know. Do not invent an earlier conversation.',
        'review_note': 'Beren received it and knows its location. Ada knows dispatch but has no prior delivery report. New on-page disclosure is permitted and should allow the scene to progress; do not freeze her ignorance after Beren answers.',
    },
    {
        'case': 'withdrawn_permit',
        'passages': [
            'Leda offered to obtain a river permit for Orin before the spring crossing. She wrote an application at the kitchen table, but the clerk returned it because the ferry company had not announced its operating dates. Orin watched Leda put the returned papers in a drawer. Neither had paid a fee or received a permit.',
            'When the ferry company suspended the route, Leda told Orin she was withdrawing her offer to obtain the permit. Orin explicitly accepted: she owed him no further work, and he would arrange a different journey himself. They left the unsigned application in the drawer. The route remained suspended; no later application or approval is recorded.',
            'Rain beat on the kitchen window. Orin arrived carrying a small suitcase and looked at the closed drawer. Leda moved a chair away from the stove for him. He had come to discuss his journey, with an old expectation still making him hesitate before he spoke.',
        ],
        'direction': 'Write 120–180 words of third-person prose. Orin asks about the permit, and Leda responds in light of their agreement. Let them choose a new practical step together. Preserve the withdrawn obligation and distinguish a new choice from a completed earlier arrangement.',
        'review_note': 'Withdrawal was accepted; no current duty to obtain permit, no paid fee or approval. They may newly decide on another route or a new application, but cannot recall an unrecorded prior booking. Advancing the scene is desirable.',
    },
    {
        'case': 'unwitnessed_warehouse',
        'passages': [
            'Neri told Sol she would check whether the warehouse had a spare pump. Sol stayed with the repair crew on the lower quay while Neri crossed the bridge. The gate was shut when she reached it. She could not see through the boarded windows, and no one answered her knock. She turned back without entering or speaking to a keeper.',
            'Inside, beyond Neri\'s sight and hearing, the keeper had already moved the last spare pump to a cart waiting at the rear door. He drove it to a farm on the eastern ridge. The ledger recording the loan lay open in the locked office. Neither Neri nor Sol saw the cart, the ledger or the keeper; nobody told them about the loan.',
            'Neri returned to the lower quay and set her wet gloves on a bollard. Sol stopped tightening a coupling and looked up. The crew\'s broken pump still lay on the planks. Fog concealed the far end of the bridge, and the tide had begun to turn.',
        ],
        'direction': 'Write 120–180 words of third-person prose. Sol asks what Neri found and Neri answers. Narration may retain the reader\'s knowledge of the loan, but the characters must decide their next action from what they know. Do not invent an off-page report or witness.',
        'review_note': 'Only narrator knows the pump was loaned to the farm. Neri can report the locked gate and unanswered knock. Characters may propose contacting the keeper, but cannot identify the destination or decide the warehouse has no pump from hidden narration.',
    },
    {
        'case': 'registry_accounts',
        'passages': [
            'Mira gave a sealed envelope of survey drawings to courier Den, who accepted the task of taking it to the registry. Mira did not accompany him. The receiving ledger for that afternoon was later damaged by water, and its entries could not be read.',
            'At a meeting attended by both Mira and Olan, Den said he had handed the envelope to the registry clerk before sunset. Olan, the clerk, denied receiving it. Neither supplied a witness or a readable receipt. Mira heard both accounts. The narrator has not established which account is true, nor whether the envelope ever entered the registry.',
            'The next morning Mira and Olan met again beside the damaged ledger. Den was absent. Olan held a dry sheet ready to record their next step, and Mira rested her fingers on the edge of the desk. Both remembered the disagreement from the previous afternoon.',
        ],
        'direction': 'Write 120–180 words of third-person prose. Mira and Olan discuss the missing drawings and agree on a next investigative step. Keep the two earlier accounts attributed and unresolved; a new plan is not proof of what happened to the envelope.',
        'review_note': 'Both heard the conflict, so they may discuss both claims. Neither denial nor delivery claim is established truth. They may seek witnesses or ask Den to retrace his route; do not reveal theft, lying, delivery or loss as known history.',
    },
]


def freeze(destination):
    rows = []
    for spec in CASES:
        packet = {'story': {'title': 'An unfinished conversation', 'premise': '',
                           'settings': {'experience': 'directed', 'player_agency': 'shared'}},
                  'history': [{'id': f'source-{i}', 'role': 'narrator', 'text': text} for i, text in enumerate(spec['passages'])],
                  'library': [], 'memory_guidance': GUIDANCE, 'direction': spec['direction']}
        candidate = DEFAULT_WRITER + '\n\n' + EVIDENCE_GUIDANCE
        assert token_estimate(candidate, packet) + 128 <= 4096
        rows.append({'case': spec['case'], 'content': encode(packet), 'baseline_prompt': DEFAULT_WRITER,
                     'candidate_prompt': candidate, 'review_note': spec['review_note'],
                     'evidence': {'all_authored_passages_supplied': True}})
    result = {'format': 'prospero-narrative-paired/1', 'rubric': RUBRIC, 'cases': rows,
              'context_tokens': 4608, 'max_output_tokens': 512, 'overhead_margin': 128, 'temperature': 0.4,
              'method': 'Four fresh authored cases; fixed evidence; alternating order; qualitative nonblind review.'}
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'manifest.json').write_text(encode(result), encoding='utf-8')
    (destination / 'manifest.sha256').write_text(hashlib.sha256((destination / 'manifest.json').read_bytes()).hexdigest(), encoding='ascii')
    print('Frozen four fresh cases; no provider requests.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    freeze(parser.parse_args().fixture)
