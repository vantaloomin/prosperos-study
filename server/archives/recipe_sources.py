"""Validate historical recipe boundaries without consulting later mutable Story choices."""
from server.archives.links import snapshot_links
from server.archives.remap import fields
from server.branches import path_nodes
from server.errors import require
from server.mechanics.state import node_state
from server.text_edits.models import TextTarget
from server.workflow.context import message_source
from server.writing.recipe_sources import source_boundary


def validate_sources(connection, run, identities):
    snapshot, bindings = run['snapshot'], run['bindings']
    sources = snapshot['sources']
    require(set(sources) == {'boundary', 'informed', 'blind', 'author_memory', 'assets', 'memory_policy', 'summary_aids', 'scene'},
            'A recipe has an unsupported source bundle.')
    boundary = fields(sources['boundary'], bindings)
    snapshot_links(connection, {'branch': boundary}, run['story_id'])
    branch = fields(snapshot['branch'], bindings)
    _, expected = source_boundary(connection, branch, run['target'])
    require(all(boundary[key] == expected[key] for key in ('id', 'story_id', 'head_id', 'manifest_id')),
            'A recipe changed its permitted historical boundary.')
    path = path_nodes(connection, boundary['head_id'])
    if run['target']['ref']['kind'] == 'passage':
        path = path[:-1]
    namespace = snapshot['branch']['story_id']
    path = [{**node, 'id': identities.node_id(node, namespace)} for node in path]
    prose = [node for node in path if node['role'] != 'ooc']
    require(sources['blind'] == [message_source(node, 'previous') for node in prose[-2:]],
            'An independent recipe reader acquired unrelated context.')
    messages = [source for source in sources['informed'] if source['id'].startswith('message:')]
    expected = [message_source(node, 'previous') for node in prose]
    expected.extend(message_source(node, 'guidance') for node in path if node['role'] == 'ooc')
    require(messages == expected, 'Recipe prose sources differ from their original permitted path.')
    for collection in ('informed', 'blind'):
        documents = sources[collection]
        require(isinstance(documents, list) and all(isinstance(item, dict) and all(isinstance(item.get(key), str)
                for key in ('id', 'kind', 'title', 'text')) for item in documents), 'Recipe sources must contain literal text and identities.')
        require(len({item['id'] for item in documents}) == len(documents), 'Recipe source identities are repeated.')
    before = snapshot['chance']['before']
    live = node_state(connection, boundary['head_id'])
    require(set(before) == set(live) and all(identities.matches(live[key], value) if key == 'last_opportunity_id'
            else live[key] == value for key, value in before.items()), 'A recipe changed its original mechanics boundary.')
    ref = TextTarget.model_validate(run['target']['ref'])
    scene = sources['scene']
    require((scene is not None) == (ref.kind == 'scene-block'), 'A recipe changed its scene context scope.')
    if scene:
        require(identities.matches(ref.scene_id, scene['id']) and scene['block_id'] == ref.item_id,
                'A recipe changed its selected scene block.')
        selected = [block for block in scene['blocks'] if block['id'] == scene['block_id']]
        require(len(selected) == 1 and selected[0]['text'] == run['target']['text'], 'A recipe scene lost its original selected wording.')
