"""Editable examples; listing them does not publish or activate configuration."""

STARTERS = [
    {'key': 'quiet-character-scene', 'name': 'Quiet character scene',
     'description': 'A small interaction carried by gesture, dialogue, and an unresolved choice.',
     'content': {'purpose': 'draft', 'instructions': 'Write a quiet character scene around {{focus}}. '
                 'Favor concrete gestures and understated dialogue. Respect the selected agency boundaries.',
                 'variables': [{'name': 'focus', 'label': 'Scene focus',
                                'description': 'The interaction or small change at the heart of this scene.',
                                'example': 'returning a borrowed key'}], 'steps': [{'task': 'writer'}]}},
    {'key': 'revise-for-tension', 'name': 'Revise for tension',
     'description': 'Increase the pressure in selected prose while preserving established events.',
     'content': {'purpose': 'revise', 'instructions': 'Revise the selected text to sharpen uncertainty, '
                 'conflicting wants, and the cost of the next choice. Preserve established events and agency. '
                 'Do not invent a threat merely to make the passage louder.', 'steps': [{'task': 'revision'}]}},
    {'key': 'dialogue-pass', 'name': 'Dialogue pass',
     'description': 'Make voices distinct and remove repeated explanations in selected dialogue.',
     'content': {'purpose': 'revise', 'instructions': 'Revise the selected dialogue for distinct voices, '
                 'subtext, and economical exchanges. Preserve who knows what and who makes each decision. '
                 'Keep the facts and outcome intact.', 'steps': [{'task': 'revision'}]}},
]
