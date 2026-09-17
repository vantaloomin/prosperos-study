from server.errors import require
from server.scenes.patch_apply import apply_edit, apply_edits


def validate_patch(result, context):
    edits = result['edits']
    require(len({edit['block_id'] for edit in edits}) == len(edits), 'Each block may be edited only once per pass.', 502)
    blocks = context['blocks']
    for edit in edits:
        validate_edit(edit, blocks, context)
        # Apply sequentially so an anchor may refer to an earlier insertion.
        blocks = [dict(block) for block in blocks]
        apply_edit(blocks, edit, context['stage'])
    apply_edits(context['blocks'], edits, context['stage'])
    validate_resolutions(result, context)


def validate_edit(edit, blocks, context):
    items = {item['id']: item for item in context['package']['items']}
    refs = edit['item_ids']
    require(len(set(refs)) == len(refs) and set(refs) <= set(items), 'A patch cites an unapproved or repeated item.', 502)
    if edit['operation'] in {'insert', 'move'}:
        require(any(items[ref]['disposition'] == 'hold' for ref in refs), 'A structural insertion or move needs an approved hold.', 502)
    block = next((block for block in blocks if block['id'] == edit['block_id']), None)
    if edit['operation'] == 'insert':
        validate_insertion(edit, block, context)
        return
    require(block is not None and edit['before'] == block['text'], 'The patch must quote the complete original block exactly.', 502)
    require(not edit['speaker'], 'An existing block cannot change speaker.', 502)
    validate_operation(edit, block, context)


def validate_insertion(edit, block, context):
    require(block is None and not edit['before'] and bool(edit['after'].strip()), 'An insertion needs a new ID, empty before and nonempty after.', 502)
    dialogue = context['stage'] == 'scene-dialogue-patch'
    require(bool(edit['speaker'].strip()) == dialogue, 'Only an inserted dialogue block needs a speaker.', 502)


def validate_operation(edit, block, context):
    operation = edit['operation']
    if operation == 'move':
        require(context['stage'] == 'scene-patch' and edit['after'] == edit['before'], 'Only prose patching may move an unchanged block.', 502)
        return
    kind = 'dialogue' if context['stage'] == 'scene-dialogue-patch' else 'prose'
    require(block['kind'] == kind, 'This specialist cannot rewrite the other writer\'s blocks.', 502)
    require(edit['anchor_id'] is None, 'Only insertions and moves accept a position.', 502)
    if operation == 'delete':
        require(not edit['after'], 'A deleted block must have empty after text.', 502)
    else:
        require(bool(edit['after'].strip()) and edit['after'] != edit['before'], 'A replacement must contain changed, nonempty prose.', 502)


def validate_resolutions(result, context):
    expected = [item['id'] for item in context['package']['items']]
    require([item['item_id'] for item in result['resolutions']] == expected, 'Account for every approved item once in package order.', 502)
    edits = result['edits'] + context.get('prior_edits', [])
    addressed = {item for edit in edits for item in edit['item_ids']}
    for item in result['resolutions']:
        require(item['status'] != 'addressed' or item['item_id'] in addressed, 'An addressed item needs a linked change.', 502)
        if item['status'] == 'defer-dialogue':
            require(context['stage'] == 'scene-patch' and context['dialogue_split'], 'Only split prose patching may defer to dialogue.', 502)


def change_texts(change):
    return [change['before'], change['after']] + [block['text'] for block in change['neighbors'] + change.get('before_neighbors', [])]


def validate_patch_check(result, context):
    changes = {change['id']: change for change in context['changes']}
    require([check['change_id'] for check in result['checks']] == list(changes), 'Check every change exactly once in supplied order.', 502)
    require([item['item_id'] for item in result['resolutions']] == [item['id'] for item in context['package']['items']],
            'Check every approved item exactly once in package order.', 502)
    for check in result['checks']:
        texts = change_texts(changes[check['change_id']])
        require(all(any(quote in text for text in texts) for quote in check['quotes']), 'A check quotation is outside its changed passage and neighbors.', 502)
    for issue in result['issues']:
        require(issue['change_id'] in changes, 'An issue cites an unknown change.', 502)
        require(any(issue['quote'] in text for text in change_texts(changes[issue['change_id']])), 'An issue quotation is outside the supplied passages.', 502)


def patch_check_passes(result):
    return bool(result) and not result['issues'] and all(check['status'] == 'pass' for check in result['checks']) and all(
        item['status'] == 'addressed' for item in result['resolutions'])
