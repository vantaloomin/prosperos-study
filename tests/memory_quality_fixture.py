"""Authored retrieval probes. Expected evidence is independent of ranking code.

These test source retrieval, not whether a writer answers correctly or respects
an unreliable narrator. Each tuple is (id, exact passage, reader's query).
"""

CASES = {
    'mystery': [
        ('m01', 'Éléonore hid the orchid medallion inside the cracked piano stool.',
         'Where did Éléonore hide the orchid medallion?'),
        ('m02', 'The inspector did not find blood on the staircase. The red stain was paint.',
         'Was the red staircase stain blood or paint?'),
        ('m03', 'A porter claimed that Vera stole the emerald. Nobody had verified his account.',
         'What was the unverified allegation about Vera and the emerald?'),
        ('m04', 'At midnight, the library clock stopped. The west door opened seven minutes later.',
         'Did the library clock stop before the west door opened?'),
        ('m05', 'Only Soren saw the forged signature. He kept it from the rest of the household.',
         'Who knew about the forged signature, and who was kept uninformed?'),
        ('m06', 'The first report named Rook as the driver. The corrected report identified Finch.',
         'Who did the corrected report identify as the driver?'),
        ('m07', 'The burnt ledger survived because Amara had wrapped it in wet sailcloth.',
         'How did Amara protect the ledger from the fire?'),
        ('m08', 'The visitor called herself Nightjar; her real name was Laila.',
         'What was Nightjar’s real name?'),
        ('m09', 'Jules promised the locksmith he would return the cobalt key after the hearing.',
         'What did Jules promise to return to the locksmith?'),
        ('m10', 'An unsigned note read: “Trust the gardener.” Its author remained unknown.',
         'Who wrote the gardener note? Preserve that the author is unknown.'),
        ('m11', 'The missing violin bore serial number VX-314; the pawnshop violin was VX-341.',
         'Distinguish VX-314 from the pawnshop instrument.'),
        ('m12', 'The murderer’s identity had not been established when the inquest adjourned.',
         'At the inquest adjournment, was the murderer known?'),
    ],
    'relationships': [
        ('r01', 'Mina promised to water Luis’s balcony rosemary while he visited his father.',
         'What promise did Mina make about Luis’s balcony?'),
        ('r02', 'Noor dislikes surprise parties. She enjoys quiet birthdays with one close friend.',
         'Would Noor prefer a surprise party or a quiet birthday?'),
        ('r03', 'The neighbors thought Dev and Ada were engaged. Dev said they were only roommates.',
         'Was the engagement between Dev and Ada confirmed or a neighbor rumor?'),
        ('r04', 'Kira apologized about the broken mug before Jo admitted borrowing the bicycle.',
         'Which came first, Kira’s apology or Jo’s bicycle admission?'),
        ('r05', 'Tess told her sister about the scholarship, but had not yet told her mother.',
         'Who knows about Tess’s scholarship, and who does not?'),
        ('r06', 'Omar first suggested Friday dinner, then corrected the invitation to Sunday lunch.',
         'What is Omar’s corrected invitation?'),
        ('r07', 'Everyone at the café calls Beatrice Bee, a nickname she chose herself.',
         'Who is Bee at the café?'),
        ('r08', '山田葵 left a folded crane beside Ren’s lunchbox as an apology.',
         'What did 山田葵 leave beside Ren’s lunchbox?'),
        ('r09', 'The two sisters agreed not to discuss the inheritance during their father’s concert.',
         'What subject did the sisters agree to avoid at the concert?'),
        ('r10', 'After the argument, Pavel put the spare apartment key in the blue teacup.',
         'Where is Pavel’s spare apartment key?'),
        ('r11', 'Alina has never learned why Marc missed the wedding. She has not asked him.',
         'Does Alina know why Marc missed the wedding?'),
        ('r12', 'Inez’s dog needs medicine at breakfast. Her cat receives no medicine.',
         'Which of Inez’s pets needs medicine at breakfast?'),
    ],
    'speculative': [
        ('s01', 'The habitat’s oxygen garden fails in ultraviolet light; ordinary sunlight is filtered.',
         'What threatens the oxygen garden in the habitat?'),
        ('s02', 'A moonstone stores heat, not light. The lantern glow comes from ordinary oil.',
         'Does moonstone store light or heat?'),
        ('s03', 'Pilgrims say the drowned satellite answers prayers. No receiver has detected a reply.',
         'Is the drowned satellite’s prayer response observed or a pilgrim belief?'),
        ('s04', 'The tidal gate closed before the second moon rose above the glacier.',
         'Did the second moon rise before or after the tidal gate closed?'),
        ('s05', 'Unit K-7 alone decoded the rebel beacon. The bridge crew still thinks it is static.',
         'Who understands the rebel beacon, and what does the bridge crew believe?'),
        ('s06', 'The old chart marked the portal as safe. A revised survey classified it as one-way.',
         'What did the revised survey establish about the portal?'),
        ('s07', 'The ferryman is known as Ash; his birth name is Tarek.',
         'Who is the ferryman called Ash?'),
        ('s08', 'Zoë promised the glasswright three unbroken lenses in exchange for sanctuary.',
         'What does Zoë owe the glasswright?'),
        ('s09', 'The archive answers only questions spoken backward in the river dialect.',
         'How must a question be spoken to the archive?'),
        ('s10', 'The expedition does not know who built the hollow star. Its builders left no names.',
         'Has the expedition identified the hollow star’s builders?'),
        ('s11', 'The android Nami cannot taste salt but can measure salinity with her fingertips.',
         'How can Nami detect salinity despite her inability to taste salt?'),
        ('s12', 'Cold iron interrupts the ward for nine breaths; silver has no effect on it.',
         'What interrupts the ward, and for how long?'),
    ],
    'travel': [
        ('t01', 'The rescue team cached yellow water drums beneath the abandoned cable station.',
         'Where are the rescue team’s water drums?'),
        ('t02', 'The rope bridge cannot hold two loaded carts. One unloaded cart crossed safely.',
         'What load limitation applies to the rope bridge?'),
        ('t03', 'A driver warned of bandits at Red Pass, but the scouts found no sign of them.',
         'What supports or contradicts the warning about bandits at Red Pass?'),
        ('t04', 'The north tunnel flooded after the convoy passed the junction, not before.',
         'When did the north tunnel flood relative to the convoy’s passage?'),
        ('t05', 'Captain Sal knows the engine will fail by dusk; the passengers have not been warned.',
         'Who knows the engine will fail, and have the passengers been told?'),
        ('t06', 'An early map placed the ford upstream. The ranger corrected it to below the mill.',
         'Where is the ford according to the ranger’s correction?'),
        ('t07', 'The courier called Red is actually Lieutenant Osei, traveling without insignia.',
         'Who is the courier using the name Red?'),
        ('t08', 'Anđela promised to wait at the third cairn until the injured climber caught up.',
         'Where did Anđela promise to wait for the injured climber?'),
        ('t09', 'The fuel gauge is broken. Nobody knows how much fuel remains in the launch.',
         'Is the launch’s remaining fuel known?'),
        ('t10', 'Emergency flares were spent during the first rescue; only a hand mirror remains.',
         'Which signaling equipment remains after the first rescue?'),
        ('t11', 'The safe route follows white markers. Blue markers lead to the quarry edge.',
         'Which markers identify the safe route rather than the quarry edge?'),
        ('t12', 'The saddlebag contains insulin wrapped in wool; it must be kept cool and dry.',
         'What medicine is in the saddlebag and how should it be stored?'),
    ],
}

# Deliberately out-of-corpus concepts. Shared function words must not create hits.
UNANSWERABLE = {
    'mystery': ['xylophone auction tariff', 'who manufactured QZ-7788?', 'tell me about malachite cryptography'],
    'relationships': ['saffron ravioli recipe', 'who founded Xylovia?', 'tell me about anaerobic triathlons'],
    'speculative': ['praseodymium isotopic abundance', 'who governs Zzyzx?', 'tell me about semaphoric mycology'],
    'travel': ['abyssal cephalopod taxonomy', 'who sponsors WQ-9911?', 'tell me about hydroponic ziggurats'],
}


def probes():
    answerable = [{'genre': genre, 'id': key, 'query': query, 'expected': [key]}
                  for genre, cases in CASES.items() for key, _text, query in cases]
    absent = [{'genre': genre, 'id': f'{genre}-absent-{index}', 'query': query, 'expected': []}
              for genre, queries in UNANSWERABLE.items() for index, query in enumerate(queries)]
    return [*answerable, *absent]


def passages():
    authored = [{'id': key, 'text': text} for cases in CASES.values() for key, text, _query in cases]
    # Strongly repetitive distractors plus overlapping topical terms. Distinct
    # IDs make repeated boilerplate consume real corpus statistics and slots.
    distractors = [{'id': f'distractor-{index}', 'text':
                   'The travelers stopped for lunch. Conversation turned to a key, a promise, '
                   'an old map and an unverified report. Nobody offered a new detail. '
                   f'They resumed the journey at marker {index}.'} for index in range(180)]
    return [*authored, *distractors]
