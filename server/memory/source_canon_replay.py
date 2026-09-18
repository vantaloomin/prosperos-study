"""Rebuild optional Canon from pinned Markdown, without reranking frozen requests."""
from server.errors import require
from server.memory.source_canon import ALGORITHM, catalog_for, coverage, project_canon


def validate_collection(selection, permitted):
    report = permitted['report']
    require({key: selection.get(key) for key in report} == report,
            'A specialist Canon receipt differs from its pinned compiler inputs.')
    spans = selection.get('spans')
    require(isinstance(spans, list), 'A specialist Canon receipt has no excerpts.')
    valid = {(chunk.start, chunk.end, chunk.digest) for chunk in permitted['chunks']}
    ranges = []
    for span in spans:
        require(isinstance(span, dict) and type(span.get('start')) is int and type(span.get('end')) is int,
                'A specialist Canon excerpt has an invalid range.')
        require((span['start'], span['end'], span.get('sha256')) in valid,
                'A specialist Canon excerpt differs from its exact pinned Markdown.')
        ranges.append((span['start'], span['end']))
    require(ranges == sorted(ranges) and all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])),
            'Specialist Canon excerpts are reordered, duplicated or overlapping.')


def replay_canon(context, receipt, assets):
    require(isinstance(receipt, dict) and receipt.get('algorithm') == ALGORITHM
            and context.get('scope') != 'blind' and assets is not None,
            'Unsupported or unbound specialist Canon receipt.')
    catalog = catalog_for(context, assets)
    collections = receipt.get('collections')
    require(isinstance(collections, list) and bool(collections)
            and all(isinstance(item, dict) and type(item.get('index')) is int for item in collections),
            'Invalid specialist Canon selection.')
    require([item['index'] for item in collections] == list(catalog),
            'Specialist Canon selection includes an unavailable or required reference.')
    for item in collections:
        validate_collection(item, catalog[item['index']])
    require(receipt.get('coverage') == coverage(collections), 'Specialist Canon coverage was altered.')
    return project_canon(context, collections)
