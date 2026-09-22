"""Editable original prompts; loading/importing a starter draws nothing."""


def starter(key, name, description, cards):
    return {'key': key, 'document': {'format': 'prospero-inspiration-pack', 'version': 1, 'name': name,
            'description': description, 'decks': [{'key': key, 'name': name, 'description': description,
                'content': {'cards': [{'id': card_id, 'title': title, 'text': text, 'tags': tags, 'weight': weight, 'enabled': True}
                                     for card_id, title, text, tags, weight in cards]}}]}}


def starters():
    return [
        starter('quiet-moments', 'Quiet character moments', 'Small actions that reveal a relationship. Weighted with replacement; nothing becomes story fact until you choose it.', [
            ('saved-seat', 'A place kept open', 'Someone has kept a seat, a portion of food, or a little time for a person who may not arrive. Let the practical choice reveal what they will not say.', ['relationship', 'ordinary'], 3),
            ('borrowed-tool', 'The borrowed tool', 'Return a borrowed object with one small repair. Explore whether the recipient notices, welcomes it, or wishes it had been left alone.', ['relationship', 'gesture'], 2),
            ('shared-task', 'A task for two', 'Give two characters a mundane task with mismatched methods. Let cooperation or friction emerge from the work itself.', ['relationship', 'ordinary'], 3),
            ('changed-habit', 'A changed habit', 'Someone quietly stops doing a familiar thing. Let another person notice the absence before either offers an explanation.', ['change', 'gesture'], 1),
            ('private-joke', 'An old joke', 'An old joke surfaces at an inconvenient moment. Decide who still finds it funny and what has changed between them.', ['relationship', 'memory'], 1),
        ]),
        starter('mystery-complications', 'Mystery complications', 'Evidence and practical obstacles that invite investigation without declaring the solution.', [
            ('wrong-time', 'The timing is wrong', 'A routine timestamp contradicts the accepted sequence. It may reflect a mistaken clock, a habit, or a lie; leave those possibilities open.', ['evidence', 'timeline'], 3),
            ('helpful-witness', 'The helpful witness', 'A witness volunteers a useful detail but insists on a seemingly minor condition before helping further. Decide what that condition costs.', ['witness', 'obstacle'], 2),
            ('ordinary-copy', 'An ordinary duplicate', 'The supposedly distinctive object has an ordinary duplicate. Ask which property actually matters to the investigation.', ['evidence', 'object'], 2),
            ('missing-routine', 'A broken routine', 'A daily service did not happen when expected: a delivery, cleaning, or check-in. Someone treated the interruption as unremarkable.', ['evidence', 'timeline'], 2),
            ('closing-window', 'A closing window', 'A source of information will soon become unavailable for a mundane reason. Force a choice about what to check first without inventing certainty.', ['obstacle', 'choice'], 1),
        ]),
        starter('speculative-encounters', 'Speculative encounters', 'Unfamiliar rules revealed through encounters. Adapt their scale and consequences to the world.', [
            ('different-measure', 'A different measure', 'A visitor values something locals overlook: heat, silence, a promise, or discarded material. Let a small exchange expose the difference.', ['encounter', 'culture'], 3),
            ('old-machine', 'The patient mechanism', 'A mechanism continues a task whose purpose has been forgotten. Its next ordinary cycle inconveniences someone who understands only part of it.', ['place', 'technology'], 2),
            ('shared-shelter', 'Shared shelter', 'An unusual environmental change forces strangers to share temporary shelter. Give them a practical problem before a grand revelation.', ['encounter', 'environment'], 3),
            ('precise-custom', 'A precise custom', 'A courteous local corrects one small act with unexpected urgency. Discover the custom through its immediate social or physical consequences.', ['encounter', 'culture'], 2),
            ('quiet-anomaly', 'The quiet anomaly', 'An everyday object behaves slightly differently in one location. Let a character test a modest hypothesis before anyone names the cause.', ['place', 'discovery'], 1),
        ]),
    ]
