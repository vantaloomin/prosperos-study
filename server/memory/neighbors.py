"""One bounded continuation, selected by proximity rather than inferred truth.

The caller supplies the complete scoped source order and an already filtered
corpus. Missing, excluded, required or ineligible chunks are barriers, not gaps
to skip across. Neighbors never recursively expand into more neighbors.
"""
from server.memory.retrieval import Hit

NEIGHBOR_REASON = 'Immediately following recalled evidence; proximity is not a verified correction.'


def following_chunk(anchor, available_chunks, source_order):
    chunks = {(chunk.source_id, chunk.start): chunk for chunk in available_chunks}
    within = chunks.get((anchor.source_id, anchor.end))
    if within:
        return within
    positions = {key: index for index, (key, _length) in enumerate(source_order)}
    index = positions[anchor.source_id]
    if anchor.end != source_order[index][1] or index + 1 >= len(source_order):
        return None
    return chunks.get((source_order[index + 1][0], 0))


def with_following_context(hits, corpus, source_order):
    if not hits:
        return hits
    anchor = hits[0]
    following = following_chunk(anchor.chunk, corpus.chunks, source_order)
    if following is None:
        return hits
    neighbor = Hit(following, 0, (), NEIGHBOR_REASON, anchor_id=anchor.chunk.id)
    # Retain an independently ranked neighbor as fallback if the anchor cannot fit.
    return [anchor, neighbor, *hits[1:]]


def anchor_present(hit, selected_ids):
    return hit.chunk.id not in selected_ids and (hit.anchor_id is None or hit.anchor_id in selected_ids)


def neighbor_receipt(hit):
    return {'adjacent_to': hit.anchor_id} if hit.anchor_id else {}
