"""Freeze planned draws once; only scene acceptance adopts their resulting state."""
import secrets
from copy import deepcopy

from server.database import decode, encode, one
from server.errors import require
from server.lore.runtime import attach_lore
from server.mechanics.config import configured_tables, read_settings
from server.mechanics.engine import disabled_reason, eligible, resolve_beat
from server.mechanics.models import Beat, RngSettings
from server.mechanics.state import node_state
from server.mechanics.storage import opportunity_stale, pending_opportunity
from server.mechanics.table_engine import TableSet
from server.scenes.chance_models import ChanceBoundary


def freeze_chance(connection, branch, story):
    settings = read_settings(story)
    pending = pending_opportunity(connection, branch, story)
    require(not pending or not opportunity_stale(pending, branch, story),
            'The prepared beat is stale. Preserve it and start from its original point or reroll on a new branch.', 409)
    tables = configured_tables(connection, settings) if settings.enabled else {}
    if tables:
        settings = settings.model_copy(update={'table_versions': {key: value['id'] for key, value in tables.items()}})
    return {'chance_version': 1, 'settings': settings.model_dump(), 'tables': tables,
            'before': node_state(connection, branch['head_id']), 'opportunity_id': pending['id'] if pending else None}


def chance_stale(story, snapshot):
    if not snapshot.get('chance_version'):
        return False
    current, frozen = read_settings(story).model_dump(), snapshot['settings']
    if any(current[key] != frozen.get(key) for key in current if key != 'table_versions'):
        return True
    return current['enabled'] and any(key in frozen['table_versions'] and frozen['table_versions'][key] != version
                                      for key, version in current['table_versions'].items())


def inherited_chance(connection, snapshot):
    opportunity_id = snapshot.get('opportunity_id')
    if not opportunity_id:
        return None
    row = one(connection, 'SELECT * FROM mechanic_opportunities WHERE id=?', (opportunity_id,))
    branch = snapshot['branch']
    require(row['story_id'] == branch['story_id'] and row['branch_id'] == branch['id']
            and row['head_key'] == (branch['head_id'] or ''), 'A scene refers to a prepared beat from another point.')
    return {'opportunity_id': opportunity_id, 'result': decode(row['snapshot'])}


def prepare_chance(connection, run, plan, seeds=None):
    snapshot = run['snapshot']
    if not snapshot.get('chance_version'):
        return None
    settings = RngSettings.model_validate(snapshot['settings'])
    inherited = inherited_chance(connection, snapshot)
    lore = snapshot.get('lore_context')
    has_lore = bool(lore and lore['books'])
    if not settings.enabled and not inherited and not has_lore:
        return None
    state = deepcopy(snapshot['before'])
    if inherited:
        state = {**inherited['result']['after'], 'last_opportunity_id': inherited['opportunity_id']}
    entries = schedule_beats(snapshot['tables'], settings, plan, state, seeds, lore) if settings.enabled or has_lore else []
    return {'before': snapshot['before'], 'inherited': inherited, 'entries': entries,
            'after': entries[-1]['result']['after'] if entries else state}


def schedule_beats(versions, settings, plan, state, seeds, lore=None):
    entries = []
    for item in (plan or {}).get('beats', []):
        boundary = ChanceBoundary.model_validate(item.get('chance') or {})
        beat = Beat(label=item['title'], **boundary.model_dump())
        blocked = eligible(beat) or disabled_reason(beat, settings, TableSet(versions, settings), False)
        if lore and lore['books']:
            blocked = eligible(beat)
        seed = next(seeds) if seeds is not None else ('not-drawn' if blocked or not settings.enabled else secrets.token_hex(16))
        result = scheduled_result(versions, settings, beat, state, seed, lore)
        entries.append({'beat_id': item['id'], 'title': item['title'], 'result': result})
        state = result['after']
    return entries


def scheduled_result(versions, settings, beat, state, seed, lore):
    effective = settings if settings.enabled else settings.model_copy(update={'chance': 0, 'handling': False, 'enabled_extras': []})
    result = resolve_beat(versions, effective, beat, state, seed)
    result['settings'] = settings.model_dump()
    return attach_lore(result, lore) if lore else result


def chance_plan(run):
    return (run['state'].get('gate_a') or {}).get('mechanics')


def chance_sources(run):
    plan = chance_plan(run)
    if not plan:
        return []
    beats = [{'beat_id': item['beat_id'], 'title': item['title'], 'instructions': item['result']['writer'],
              'skip_reason': item['result']['eligibility']} for item in plan['entries']]
    inherited = plan['inherited']
    content = {'status': 'Planned constraints, not accepted events. Reuse without new draws; no-event means no replacement.',
               'prepared_opening': inherited['result']['writer'] if inherited else None, 'beats': beats}
    return [{'id': 'scene:saved-chance', 'kind': 'planned mechanics', 'title': 'Saved chance for the approved plan', 'text': encode(content)}]


def scene_mechanics_state(run):
    plan = chance_plan(run)
    return plan['after'] if plan else None
