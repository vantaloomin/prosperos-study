"""Read the first development writing receipt without changing its saved bytes."""
from server.errors import require
from server.prompts import ALL_PROMPT_LABELS
from server.writing.models import RecipeContent
from server.writing.variables import render, value_for


def resolved_legacy(guidance):
    if guidance['recipe'] is None:
        return None
    content = RecipeContent.model_validate(guidance['recipe']['content'])
    recorded = guidance['resolved_recipe']
    variables = recorded['variables']
    require(isinstance(variables, dict) and set(variables) == {item.name for item in content.variables},
            'Legacy writing variables differ from the recipe.')
    for variable in content.variables:
        value = variables[variable.name]
        require(isinstance(value, str) and len(value) <= 12000 and '\x00' not in value,
                'Invalid legacy writing variable.')
        raw = float(value) if variable.type == 'number' and value else value
        value_for(variable, raw)
    disabled = recorded['disabled_tasks']
    require(isinstance(disabled, list) and disabled == sorted(set(disabled))
            and set(content.disabled_tasks) <= set(disabled) <= set(ALL_PROMPT_LABELS),
            'Legacy writing task switches are invalid.')
    return {**content.model_dump(), 'variables': variables, 'disabled_tasks': disabled,
            'instructions': render(content.instructions, variables),
            'steps': [{**step.model_dump(), 'instructions': render(step.instructions, variables)}
                      for step in content.steps]}
