"""Separate supported settings from retained, non-executing extensions."""
from copy import deepcopy

from server.mechanics.models import RngSettings
from server.writing.extras import validate_extras
from server.writing.models import RecipeContent, RecipeStep, Sample, StyleContent, Variable
from server.writing.resources import parse_content


def split_object(raw, model, path, extras):
    if not isinstance(raw, dict):
        return raw
    known = {}
    for key, value in raw.items():
        if key in model.model_fields:
            known[key] = deepcopy(value)
        else:
            extras[f'{path}.{key}'] = deepcopy(value)
    return known


def supported_content(item):
    extras = deepcopy(item.unsupported)
    extras.update({f'resource.{key}': value for key, value in item.model_extra.items()})
    model = StyleContent if item.kind == 'style' else RecipeContent
    content = split_object(item.content, model, 'content', extras)
    children = [('examples', Sample)] if item.kind == 'style' else [('variables', Variable), ('steps', RecipeStep)]
    for field, child in children:
        if isinstance(content.get(field), list):
            content[field] = [split_object(value, child, f'content.{field}[{index}]', extras)
                              for index, value in enumerate(content[field])]
    if item.kind == 'recipe' and isinstance(content.get('randomness'), dict):
        content['randomness'] = split_object(content['randomness'], RngSettings, 'content.randomness', extras)
    return parse_content(item.kind, content), validate_extras(extras)
