from copy import deepcopy

from server.errors import require


def compose(blocks):
    return '\n\n'.join(block['text'] for block in blocks)


def apply_edits(blocks, edits, stage):
    result = deepcopy(blocks)
    changes = []
    for edit in edits:
        before_order = [block['id'] for block in result]
        before = next((block for block in result if block['id'] == edit['block_id']), None)
        neighbors = original_neighbors(edit, result, before_order)
        apply_edit(result, edit, stage)
        if edit['operation'] == 'move':
            require(before_order != [block['id'] for block in result], 'A move must change the block order.', 502)
        after = next((block for block in result if block['id'] == edit['block_id']), None)
        changes.append({**edit, 'id': f"{stage}:{edit['block_id']}", 'stage': stage,
                        'before_block': before, 'after_block': after, 'before_order': before_order,
                        'before_neighbors': neighbors,
                        'after_order': [block['id'] for block in result]})
    require(bool(result) and len(result) <= 400, 'A patch must retain between 1 and 400 blocks.', 502)
    require(len(compose(result)) <= 100000, 'The patched scene exceeds 100,000 characters.', 502)
    return result, changes


def original_neighbors(edit, blocks, ids):
    if edit['operation'] == 'insert':
        index = 0 if edit['anchor_id'] is None else ids.index(edit['anchor_id']) + 1
        return blocks[max(0, index - 1):index + 1]
    index = ids.index(edit['block_id'])
    return blocks[max(0, index - 1):index] + blocks[index + 1:index + 2]


def apply_edit(blocks, edit, stage):
    operation = edit['operation']
    if operation == 'insert':
        block = {'id': edit['block_id'], 'kind': edit.get('kind') or ('dialogue' if stage == 'scene-dialogue-patch' else 'prose'), 'text': edit['after']}
        if block['kind'] == 'dialogue':
            block.update(speaker=edit['speaker'], instruction=edit['reason'])
        insert_after(blocks, block, edit['anchor_id'])
        return
    index = next(index for index, block in enumerate(blocks) if block['id'] == edit['block_id'])
    block = blocks[index]
    if operation == 'replace':
        blocks[index] = {**block, 'text': edit['after']}
    else:
        blocks.pop(index)
        if operation == 'move':
            insert_after(blocks, block, edit['anchor_id'])


def insert_after(blocks, block, anchor):
    ids = [item['id'] for item in blocks]
    require(anchor is None or anchor in ids, 'A patch position refers to an unavailable block.', 502)
    index = 0 if anchor is None else ids.index(anchor) + 1
    blocks.insert(index, block)


def passage_changes(changes, final_blocks):
    result = []
    final_ids = [block['id'] for block in final_blocks]
    for change in changes:
        neighbors = neighbor_blocks(change, final_blocks, final_ids)
        result.append({key: value for key, value in {**change, 'neighbors': neighbors}.items()
                       if key not in {'before_order', 'after_order'}})
    return result


def neighbor_blocks(change, blocks, final_ids):
    block_id = change['block_id']
    if block_id in final_ids:
        index = final_ids.index(block_id)
        return blocks[max(0, index - 1):index] + blocks[index + 1:index + 2]
    order = change['before_order']
    index = order.index(block_id)
    before = next((item for item in reversed(order[:index]) if item in final_ids), None)
    after = next((item for item in order[index + 1:] if item in final_ids), None)
    return [block for block in blocks if block['id'] in {before, after}]
