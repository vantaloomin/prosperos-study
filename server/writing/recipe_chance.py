"""A recipe chance result belongs to its draft, never to accepted Story state."""
import secrets

from server.mechanics.engine import resolve_beat
from server.mechanics.models import Beat, RngSettings


def resolve_chance(spec, *, seed=None):
    if not spec['applicable'] or spec['beat'] is None:
        return None
    return resolve_beat(spec['tables'], RngSettings.model_validate(spec['settings']),
                        Beat.model_validate(spec['beat']), spec['before'], seed or secrets.token_hex(16))
