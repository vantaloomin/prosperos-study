"""Authored evidence expectations for comparative recall; no model or ranker labels.

The fixture is a closed-world retrieval exercise, not a generated-story quality
rubric. Reviewed cues are explicit fixture inputs, not inferred facts. Expected
quotes are authored before running the scorer and can require multiple passages.
"""

from tests.memory_quality_fixture import CASES, passages, probes

FEATURES = {
    'mystery': ['unicode', 'negation', 'rumor', 'temporal_order', 'withheld_knowledge',
                'correction', 'causality', 'alias', 'old_promise', 'unknown', 'identifier', 'unknown'],
    'relationships': ['old_promise', 'negation', 'rumor', 'temporal_order', 'withheld_knowledge',
                      'correction', 'alias', 'unicode', 'negation', 'location', 'unknown', 'negation'],
    'speculative': ['constraint', 'negation', 'rumor', 'temporal_order', 'withheld_knowledge',
                    'correction', 'alias', 'old_promise', 'constraint', 'unknown', 'negation', 'constraint'],
    'travel': ['location', 'constraint', 'rumor', 'temporal_order', 'withheld_knowledge',
               'correction', 'alias', 'old_promise', 'unknown', 'correction', 'constraint', 'constraint'],
}

# id, genre, features, query, sources, required exact evidence. A source is
# (id, text, reviewed summary, reviewed aliases). Nothing is labeled by a ranker.
CHALLENGES = [
    ('m-alias', 'mystery', ['reviewed_alias'], 'Where did the Wren place the verdict?',
     [('wren', 'Celia put the verdict under a loose hearthstone.', '', ['The Wren'])],
     [('wren', 'Celia put the verdict under a loose hearthstone.')]),
    ('m-summary', 'mystery', ['reviewed_summary', 'paraphrase'], 'Recall the breach of professional secrecy.',
     [('secrecy', 'The physician passed her patient’s sealed chart to a reporter.',
       'A breach of professional secrecy.', [])],
     [('secrecy', 'The physician passed her patient’s sealed chart to a reporter.')]),
    ('m-pair', 'mystery', ['correction', 'paired_evidence'], 'Preserve both accounts of the garnet cufflink.',
     [('garnet-rumor', 'The valet alleged that Sima had taken the garnet cufflink.', '', []),
      ('garnet-correction', 'At the hearing, the valet retracted that allegation. Sima had taken nothing.', '', [])],
     [('garnet-rumor', 'The valet alleged that Sima had taken the garnet cufflink.'),
      ('garnet-correction', 'At the hearing, the valet retracted that allegation. Sima had taken nothing.')]),
    ('m-long', 'mystery', ['long_passage'], 'Which locker holds the heliotrope dossier?',
     [('dossier', 'The heliotrope dossier is in locker 83, behind the false back.', '', [])],
     [('dossier', 'The heliotrope dossier is in locker 83, behind the false back.')]),
    ('r-alias', 'relationships', ['reviewed_alias'], 'What did the family call Aunt Junebug’s gift?',
     [('junebug', 'Marisol called her gift a reconciliation quilt.', '', ['Aunt Junebug'])],
     [('junebug', 'Marisol called her gift a reconciliation quilt.')]),
    ('r-summary', 'relationships', ['reviewed_summary', 'paraphrase'], 'Recall their tentative reconciliation.',
     [('reconciliation', 'Evan set two cups on the counter. Ruth sat down beside him for the first time in weeks.',
       'A tentative reconciliation after estrangement.', [])],
     [('reconciliation', 'Evan set two cups on the counter. Ruth sat down beside him for the first time in weeks.')]),
    ('r-pair', 'relationships', ['temporal_order', 'paired_evidence'], 'Distinguish the canceled and current arrangements for Nadine’s recital.',
     [('recital-old', 'Nadine’s recital was advertised for Thursday evening.', '', []),
      ('recital-new', 'The organizer moved it to Saturday morning. The previous announcement was canceled.', '', [])],
     [('recital-old', 'Nadine’s recital was advertised for Thursday evening.'),
      ('recital-new', 'The organizer moved it to Saturday morning. The previous announcement was canceled.')]),
    ('r-long', 'relationships', ['long_passage'], 'Where did Dalia leave the anniversary photograph?',
     [('photograph', 'Dalia tucked the anniversary photograph into the green cookbook.', '', [])],
     [('photograph', 'Dalia tucked the anniversary photograph into the green cookbook.')]),
    ('s-alias', 'speculative', ['reviewed_alias'], 'What power can the Choir-of-Ash exercise?',
     [('choir', 'The station collective can suspend the magnetic lattice for six heartbeats.', '', ['Choir-of-Ash'])],
     [('choir', 'The station collective can suspend the magnetic lattice for six heartbeats.')]),
    ('s-summary', 'speculative', ['reviewed_summary', 'paraphrase'], 'Recall the first-contact misunderstanding.',
     [('first-contact', 'When the visitors raised empty palms, the council mistook their greeting for surrender.',
       'A first-contact misunderstanding between cultures.', [])],
     [('first-contact', 'When the visitors raised empty palms, the council mistook their greeting for surrender.')]),
    ('s-pair', 'speculative', ['rumor', 'paired_evidence'], 'Preserve the prophecy and contrary observation about the aurora vault.',
     [('vault-belief', 'The acolytes believed that opening the aurora vault would end the winter.', '', []),
      ('vault-observation', 'Its doors opened. Snow continued falling for another month.', '', [])],
     [('vault-belief', 'The acolytes believed that opening the aurora vault would end the winter.'),
      ('vault-observation', 'Its doors opened. Snow continued falling for another month.')]),
    ('s-long', 'speculative', ['long_passage', 'identifier'], 'What does relay Ψ-17 do?',
     [('relay', 'Relay Ψ-17 disconnects the eastern gravity anchors; Ψ-71 controls the lights.', '', [])],
     [('relay', 'Relay Ψ-17 disconnects the eastern gravity anchors; Ψ-71 controls the lights.')]),
    ('t-alias', 'travel', ['reviewed_alias'], 'Where is the Widow’s Stair crossing?',
     [('crossing', 'The basalt switchback begins above the disused pumphouse.', '', ['Widow’s Stair'])],
     [('crossing', 'The basalt switchback begins above the disused pumphouse.')]),
    ('t-summary', 'travel', ['reviewed_summary', 'paraphrase'], 'Recall the improvised cold-chain protection.',
     [('cold-chain', 'Leena wrapped the ampoules in damp cloth and lowered them into the shaded well.',
       'Improvised cold-chain protection for medicine.', [])],
     [('cold-chain', 'Leena wrapped the ampoules in damp cloth and lowered them into the shaded well.')]),
    ('t-pair', 'travel', ['correction', 'paired_evidence'], 'Keep the initial and corrected assessment of Nacre Pass.',
     [('pass-old', 'The first scout reported that Nacre Pass was blocked by ice.', '', []),
      ('pass-new', 'Her replacement found a walkable ledge on the southern face. The earlier report was incomplete.', '', [])],
     [('pass-old', 'The first scout reported that Nacre Pass was blocked by ice.'),
      ('pass-new', 'Her replacement found a walkable ledge on the southern face. The earlier report was incomplete.')]),
    ('t-long', 'travel', ['long_passage'], 'What is stored beside the carnelian milepost?',
     [('milepost', 'Two sealed respirators are buried beside the carnelian milepost.', '', [])],
     [('milepost', 'Two sealed respirators are buried beside the carnelian milepost.')]),
    ('unicode-composed', 'mystery', ['unicode'], 'Where did E\u0301le\u0301onore hide the orchid medallion?', [],
     [('m01', 'Éléonore hid the orchid medallion inside the cracked piano stool.')]),
    ('unicode-japanese', 'relationships', ['unicode', 'non_english'], '葵の鍵はどこにありますか？',
     [('jp-key', '葵の鍵は青い引き出しにあります。', '', [])],
     [('jp-key', '葵の鍵は青い引き出しにあります。')]),
    ('thread-promise', 'speculative', ['old_promise', 'thread_only'], 'Continue their quiet reunion.',
     [('promise', 'Neris pledged to bring Esra a living seed from the sealed orchard.', '', [])],
     [('promise', 'Neris pledged to bring Esra a living seed from the sealed orchard.')]),
    ('recent-cue', 'travel', ['recent_query'], 'Continue their quiet reunion.',
     [('talisman', 'The verdigris talisman admits its bearer through the northern sluice.', '', [])],
     [('talisman', 'The verdigris talisman admits its bearer through the northern sluice.')]),
    ('m-absent-overlap', 'mystery', ['unanswerable_overlap'], 'Who manufactured the orchid medallion?', [], []),
    ('r-absent-overlap', 'relationships', ['unanswerable_overlap'], 'Who paid for Nadine’s first violin?', [], []),
    ('s-absent-overlap', 'speculative', ['unanswerable_overlap'], 'Which engineer designed relay Ψ-17?', [], []),
    ('t-absent-overlap', 'travel', ['unanswerable_overlap'], 'Who originally built the Nacre Pass bridge?', [], []),
]

LONG_FILLER = 'The procession moved slowly. People adjusted their coats and waited for the next bell. '


def challenge_sources():
    result = []
    for _key, _genre, features, _query, sources, _expected in CHALLENGES:
        for key, text, summary, aliases in sources:
            if 'long_passage' in features:
                text = LONG_FILLER * 100 + '\n\n' + text + '\n\n' + LONG_FILLER * 20
            result.append({'id': key, 'text': text, 'summary': summary, 'aliases': aliases})
    return result


def evaluation_sources():
    original = passages()
    return [*original[:48], *challenge_sources(), *original[48:]]


def evaluation_probes():
    originals = {key: (text, FEATURES[genre][index]) for genre, rows in CASES.items()
                 for index, (key, text, _query) in enumerate(rows)}
    result = []
    for probe in probes():
        expected = [{'source_id': key, 'quote': originals[key][0]} for key in probe['expected']]
        feature = originals[probe['id']][1] if expected else 'unanswerable_disjoint'
        result.append({**probe, 'expected': expected, 'features': [feature], 'origin': 'original'})
    for key, genre, features, query, _sources, expected in CHALLENGES:
        result.append({'id': key, 'genre': genre, 'features': features, 'query': query, 'origin': 'challenge',
                       'expected': [{'source_id': source, 'quote': quote} for source, quote in expected]})
    return result
