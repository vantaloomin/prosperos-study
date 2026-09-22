"""Small, literal variable substitution. Values never become executable templates."""
import math
import re

from server.errors import require

TOKEN = re.compile(r'\{\{([a-z][a-z0-9_]{0,39})\}\}')
ESCAPES = {'{{{{': '\x00OPEN\x00', '}}}}': '\x00CLOSE\x00'}


def protected(template):
    require('\x00' not in template, 'Prompt templates cannot contain null characters.')
    for literal, marker in ESCAPES.items():
        template = template.replace(literal, marker)
    return template


def names_in(template):
    source = protected(template)
    require('{{' not in TOKEN.sub('', source) and '}}' not in TOKEN.sub('', source),
            'Use {{variable_name}} for variables or {{{{ and }}}} for literal double braces.')
    return set(TOKEN.findall(source))


def value_for(variable, raw):
    if raw is None or raw == '':
        require(not variable.required, f'Enter a value for {variable.label}.')
        return ''
    if variable.type == 'number':
        require(type(raw) in (int, float) and math.isfinite(raw),
                f'{variable.label} needs a finite number.')
        return str(raw)
    require(isinstance(raw, str) and len(raw) <= 12000 and '\x00' not in raw,
            f'{variable.label} needs text of at most 12,000 characters.')
    if variable.type == 'choice':
        require(raw in variable.choices, f'Choose a listed value for {variable.label}.')
    return raw


def resolve_variables(variables, supplied):
    require(set(supplied) <= {item.name for item in variables}, 'Unknown recipe variable.')
    return {item.name: value_for(item, supplied.get(item.name, item.default)) for item in variables}


def render(template, values):
    require(names_in(template) <= set(values), 'The recipe references an undeclared variable.')
    result = TOKEN.sub(lambda match: values[match[1]], protected(template))
    for literal, marker in ESCAPES.items():
        result = result.replace(marker, literal[:2])
    return result
