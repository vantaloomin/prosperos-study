from pydantic import ValidationError

from server.database import decode
from server.errors import require
from server.mechanics.models import RngSettings
from server.mechanics.tables import catalog, validate_graph

TEXTURES = {"small-wrongs", "small-rights", "interruptions", "who-shows-up"}


def read_settings(story):
    return parse_settings(decode(story["settings"]).get("randomness", {}))


def parse_settings(raw):
    # The initial onboarding stored the explicit string "off" before the mechanics schema existed.
    if raw == "off":
        raw = {}
    try:
        return RngSettings.model_validate(raw)
    except ValidationError:
        require(False, "This story's randomness settings are invalid. Restore them in Randomness.", 409)


def normalize_story_settings(settings):
    if "randomness" not in settings:
        return settings
    return {**settings, "randomness": parse_settings(settings["randomness"]).model_dump()}


def configured_tables(connection, settings):
    versions = catalog(connection, settings.table_versions)
    definitions = {key: value["definition"] for key, value in versions.items()}
    for key in definitions:
        validate_graph(definitions, key)
    references = [*settings.disabled_tables, *settings.enabled_extras, *settings.texture_tables.values()]
    require(all(key in versions for key in references), "A configured table could not be found.")
    require(set(settings.texture_tables) <= TEXTURES, "Unknown texture purpose.")
    for key, excluded in settings.excluded_rows.items():
        require(key in definitions, "An excluded result belongs to an unknown table.")
        ids = {row["id"] for row in definitions[key]["rows"]}
        ids.update(value["id"] for field in ["low_overflow", "high_overflow"]
                   if (value := definitions[key].get(field)))
        require(set(excluded) <= ids, "An excluded result is missing from its selected table version.")
    return versions
