from copy import deepcopy

import pytest

from server.database import encode
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_knowledge_references import adopt, fixture, grant, publish, sources
from tests.test_memory_controls import entry, save, view
from tests.test_story_summaries import fork


def setup(client):
    story, first, second, book = fixture(client)
    branch = story['branch_id']
    for text in ('At the ferry, Mara says the fare is three copper coins.',
                 'At the ferry, Ivo insists the fare is five silver coins.'):
        append(client, branch, text, client.get('/api/branches/' + branch).json()['revision'])
    prose = client.get('/api/branches/' + branch + '/memory-control-sources').json()['items']
    decisions = [
        entry([prose[1]], stance='knows', character_id=first['asset_id'], text='Elin heard Mara’s copper fare account.'),
        entry([prose[2]], stance='believes', character_id=second['asset_id'], text='Elin believes the silver fare account, which may be false.'),
        entry([prose[1]], stance='unaware', character_id=second['asset_id'], text='Elin did not hear Mara’s account.'),
        entry([prose[0]], stance='knows', subject='Observer', text='Observer reached the shore.'),
        entry(prose[1:], kind='conflict', stance='intentional', subject='Ferry fare', text='Keep the incompatible fare accounts as intentional ambiguity.'),
        grant(client, story, first, book),
    ]
    save(client, branch, decisions)
    keys = ['character:' + first['asset_id'], 'character:' + second['asset_id'], 'name:observer']
    return story, first, second, book, prose, decisions, keys


def catalogue(client, branch):
    result = client.get('/api/branches/' + branch + '/memory-rehearsal')
    assert result.status_code == 200, result.text
    return result.json()


def request(client, branch, **extra):
    current = catalogue(client, branch)['boundary']
    return {'expected_revision': current['revision'], 'expected_version_id': current['version_id'], 'query': 'ferry fare', **extra}


def rehearsal(client, branch, **extra):
    response = client.post('/api/branches/' + branch + '/memory-rehearsal', json=request(client, branch, **extra))
    assert response.status_code == 200, response.text
    return response.json()


def test_rehearsal_distinguishes_knowledge_ignorance_and_no_grant_without_changing_authority(client):
    story, _, _, _, prose, decisions, keys = setup(client)
    branch = story['branch_id']
    before = client.get('/api/branches/' + branch).json()
    controls = view(client, branch)
    with client.app.state.database.connect() as connection:
        rows_before = list(connection.iterdump())
    report = rehearsal(client, branch, views=keys)
    first = next(item for item in report['items'] if item['source']['id'] == prose[1]['id'])
    assert [cell['states'] for cell in first['knowledge']] == [['knows'], ['unaware'], ['unrecorded']]
    assert first['different_states']
    second = next(item for item in report['items'] if item['source']['id'] == prose[2]['id'])
    assert second['knowledge'][1]['states'] == ['believes']
    assert report['conflicts'][0]['stance'] == 'intentional'
    assert [source['text'] for source in report['conflicts'][0]['sources']] == [source['text'] for source in prose[1:]]
    assert any(item['id'] == decisions[1]['id'] and 'may be false' in item['text'] for item in report['decisions'])
    assert client.get('/api/branches/' + branch).json() == before
    assert view(client, branch) == controls
    with client.app.state.database.connect() as connection:
        assert list(connection.iterdump()) == rows_before
        for table in ('scene_runs', 'generations', 'summary_runs', 'mechanic_opportunities'):
            assert connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


def test_same_name_characters_do_not_merge_and_name_only_views_match_case_insensitively(client):
    story, first, second, _, _, _, keys = setup(client)
    views = catalogue(client, story['branch_id'])['views']
    assert {item['character_id'] for item in views if item['subject'] == 'Elin'} == {first['asset_id'], second['asset_id']}
    report = rehearsal(client, story['branch_id'], query='shore', views=[keys[2]])
    assert any(item['knowledge'][0]['states'] == ['knows'] for item in report['items'])


def test_reference_search_is_explicit_and_excludes_ineligible_fields_and_collections(client):
    story, _, _, _, _, _, keys = setup(client)
    ordinary = rehearsal(client, story['branch_id'], views=keys)
    references = rehearsal(client, story['branch_id'], views=keys, include_library=True)
    assert all('node_id' in item['source'] for item in ordinary['items'])
    assert any(item['source'].get('field') == 'text' and item['source'].get('edition') == 1 for item in references['items'])
    assert references['source_count'] > ordinary['source_count']
    report = rehearsal(client, story['branch_id'], query='SECRET', include_library=True)
    text = '\n'.join(item['source']['text'] for item in report['items'])
    assert 'author instruction' not in text and 'greeting' not in text and 'extra metadata' not in text and 'DISABLED' not in text


def test_sibling_and_other_story_sources_do_not_affect_ranking_counts_or_views(client):
    story, _, _, _, _, _, keys = setup(client)
    branch = story['branch_id']
    prior = rehearsal(client, branch, views=keys, include_library=True)
    sibling = fork(client, branch, prior['boundary']['head_id'])
    append(client, sibling, 'FOREIGN ferry fare copper silver ' * 30, client.get('/api/branches/' + sibling).json()['revision'])
    save(client, sibling, [])
    fixture(client)
    assert rehearsal(client, branch, views=keys, include_library=True) == prior


def test_past_edit_and_historical_forks_do_not_reveal_future_decisions_or_sources(client):
    story, _, _, _, prose, _, _ = setup(client)
    earlier = fork(client, story['branch_id'], prose[0]['node_id'])
    report = rehearsal(client, earlier)
    assert not report['items'] and not report['conflicts'] and not report['decisions']
    assert report['source_count'] == 1
    edited = fork(client, story['branch_id'], prose[1]['node_id'], 'A different route through the orchard.')
    report = rehearsal(client, edited)
    assert not report['items'] and not report['conflicts'] and not report['decisions']


def test_disabled_decisions_do_not_supply_query_cues_or_conflict_claims(client):
    story, _, _, _, _, decisions, keys = setup(client)
    save(client, story['branch_id'], [{**item, 'enabled': False} for item in decisions])
    report = rehearsal(client, story['branch_id'], query='incompatible ambiguity', views=keys[:2])
    assert not report['items'] and not report['conflicts'] and not report['decisions']
    report = rehearsal(client, story['branch_id'], views=keys[:2])
    assert all(cell['states'] == ['unrecorded'] for item in report['items'] for cell in item['knowledge'])


def test_source_counts_are_complete_but_results_are_bounded_and_absence_is_explicit(client):
    story, *_ = setup(client)
    report = rehearsal(client, story['branch_id'], limit=1)
    assert len(report['items']) == 1 and report['more_matches'] and report['source_count'] == 3
    empty = rehearsal(client, story['branch_id'], query='xylophonist quasar aardvark')
    assert not empty['items'] and not empty['more_matches'] and not empty['conflicts']


@pytest.mark.parametrize('change', ['revision', 'decisions', 'view', 'duplicate', 'empty', 'too-many', 'limit'])
def test_invalid_or_stale_rehearsals_fail_without_story_changes(client, change):
    story, _, _, _, _, _, keys = setup(client)
    branch = story['branch_id']
    body = request(client, branch, views=keys)
    if change == 'revision':
        body['expected_revision'] -= 1
    elif change == 'decisions':
        save(client, branch, [])
    elif change == 'view':
        body['views'] = ['character:not-attached']
    elif change == 'duplicate':
        body['views'] += [keys[0]]
    elif change == 'empty':
        body['query'] = '   '
    elif change == 'too-many':
        body['views'] = [str(index) for index in range(9)]
    else:
        body['limit'] = 13
    before = client.get('/api/branches/' + branch).json()
    response = client.post('/api/branches/' + branch + '/memory-rehearsal', json=body)
    assert response.status_code in {409, 422}, response.text
    assert client.get('/api/branches/' + branch).json() == before


def test_changed_reference_edition_retains_denial_without_disclosing_unavailable_interpretation(client):
    story, first, _, book, prose, decisions, keys = setup(client)
    reference = next(source for source in sources(client, story['branch_id']) if source.get('asset_id') == book['asset_id'] and 'copper coins' in source['text'])
    denial = entry([prose[1], reference], character_id=first['asset_id'], text='UNAVAILABLE_INTERPRETATION from an old edition.')
    save(client, story['branch_id'], [*decisions, denial])
    updated = publish(client, book, content={'text': 'A NEW_EDITION ferry accepts tickets.'})
    adopt(client, updated)
    report = rehearsal(client, story['branch_id'], views=keys, include_library=True)
    row = next(item for item in report['items'] if item['source']['id'] == prose[1]['id'])
    assert row['knowledge'][0]['states'] == ['unaware'] and denial['id'] in row['knowledge'][0]['decision_ids']
    assert 'UNAVAILABLE_INTERPRETATION' not in encode(report)
    assert report['unavailable_decisions'] == 2
    assert any('NEW_EDITION' in item['source']['text'] for item in report['items'])


def test_rehearsal_after_archive_restore_keeps_meaning_and_new_live_source_links(client):
    story, _, _, _, _, _, keys = setup(client)
    report = rehearsal(client, story['branch_id'], views=keys, include_library=True)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored_keys = ['character:' + mapping[key[10:]] if key.startswith('character:') else key for key in keys]
    restored = rehearsal(client, mapping[story['branch_id']], views=restored_keys, include_library=True)
    assert restored['boundary']['version_id'] == mapping[report['boundary']['version_id']]
    assert sorted(item['source']['text'] for item in restored['items']) == sorted(item['source']['text'] for item in report['items'])
    for item in restored['items']:
        original = next(old for old in report['items'] if old['source']['text'] == item['source']['text'])
        assert [cell['states'] for cell in item['knowledge']] == [cell['states'] for cell in original['knowledge']]
    again = deepcopy(restored)
    assert again == rehearsal(client, mapping[story['branch_id']], views=restored_keys, include_library=True)
