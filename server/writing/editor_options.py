"""Read-only authoring choices derived from the existing workflow catalogs."""
from server.mechanics.models import RngSettings
from server.prompts import ALL_PROMPT_LABELS
from server.roles import BLIND_LENSES, INFORMED_LENSES
from server.section_prompts import SECTION_LABELS
from server.workflow.catalog import LENSES


def recipe_editor_options():
    return {
        'lenses': [{**LENSES[key], 'scope': scope}
                   for scope, keys in [('blind', BLIND_LENSES), ('informed', INFORMED_LENSES)]
                   for key in keys],
        'tasks': [{'key': key, 'name': name} for key, name in ALL_PROMPT_LABELS.items()
                  if key not in SECTION_LABELS],
        'randomness_defaults': RngSettings().model_dump(),
    }
