from server.errors import require
from server.lore.scene import planned_sources
from server.scenes.chance import chance_sources
from server.scenes.patch_context import patch_view


def continuity_inputs(connection, run):
    patch = patch_view(connection, run)
    require(patch and patch['checked'], 'Choose a passing changed-passage check before continuity proposals.', 409)
    source = {'id': 'scene:checked', 'kind': 'proposed checked scene', 'title': 'Checked scene', 'text': patch['text']}
    return {'stage': 'scene-continuity', 'sources': planned_sources(run, [*run['snapshot']['sources'], *chance_sources(run), source]),
            'existing_entries': run['snapshot'].get('continuity', {}).get('entries', [])}
