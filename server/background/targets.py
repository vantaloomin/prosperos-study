from server.mechanics.table_engine import qualitative


def private_targets(snapshot):
    drives = []
    for index, item in enumerate(snapshot['result']['drives']):
        cues = [cue for result in item['results'] for cue in (qualitative(result) or [])]
        if snapshot['drives_enabled'] and cues:
            drives.append({'id': f'drive:{index}', 'character': item['character'], 'cues': cues})
    hooks = [{'id': f'hook:{index}', 'day': item['day'], 'cues': qualitative(item['result'])}
             for index, item in enumerate(snapshot['result']['hooks'])
             if snapshot['hooks_enabled'] and item['day'] is not None]
    return {'drives': drives, 'hooks': hooks}


def interpreted_guidance(snapshot):
    selected = snapshot.get('interpretation')
    if not selected:
        return {}
    targets = private_targets(snapshot)
    result = {}
    for kind, entries in targets.items():
        available = {item['target_id']: item for item in selected['content'][kind]}
        result[kind] = [{**item, **available[item['id']]} for item in entries if item['id'] in available]
    return {'selected_private_interpretation': result,
            'interpretation_rule': 'Keep these selected private details consistent across responses. Do not reinterpret the generic cues. '
            'They are potential motives/events, not established facts; respect dates, conditions, agency and accepted canon.'}
