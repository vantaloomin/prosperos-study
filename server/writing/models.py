from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StrictFloat, StrictStr, StringConstraints, model_validator

from server.models import Input

Text = Annotated[str, StringConstraints(max_length=12000, strip_whitespace=False)]
Choice = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class Sample(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    label: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=20000)


class StyleContent(Input):
    prose: Text = ''
    viewpoint: Text = ''
    tense: Text = ''
    dialogue: Text = ''
    rhythm: Text = ''
    description: Text = ''
    avoid: Text = ''
    examples: list[Sample] = Field(default_factory=list, max_length=8)


class Variable(Input):
    name: str = Field(pattern=r'^[a-z][a-z0-9_]{0,39}$')
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    example: str = Field(default='', max_length=2000)
    type: Literal['text', 'number', 'choice'] = 'text'
    required: bool = True
    choices: list[str] = Field(default_factory=list, max_length=30)
    default: StrictStr | StrictFloat | None = None

    @model_validator(mode='after')
    def consistent(self):
        if self.type == 'choice' and (not self.choices or len(set(self.choices)) != len(self.choices)):
            raise ValueError('A choice variable needs distinct choices.')
        if self.type != 'choice' and self.choices:
            raise ValueError('Only choice variables can declare choices.')
        if any(not choice or len(choice) > 200 for choice in self.choices):
            raise ValueError('Choices must have 1 to 200 characters.')
        return self


class RecipeStep(Input):
    task: Literal['writer', 'review', 'revision']
    instructions: Text = ''
    profile_id: str | None = Field(default=None, min_length=1, max_length=100)
    lenses: list[str] = Field(default_factory=list, max_length=12)


class RecipeContent(Input):
    purpose: Literal['draft', 'review', 'revise'] = 'draft'
    instructions: Text = ''
    style: Choice = 'inherit'
    variables: list[Variable] = Field(default_factory=list, max_length=20)
    steps: list[RecipeStep] = Field(default_factory=list, max_length=8)
    disabled_tasks: list[str] = Field(default_factory=list, max_length=100)
    randomness: dict | None = None

    @model_validator(mode='after')
    def distinct_variables(self):
        names = [item.name for item in self.variables]
        if len(names) != len(set(names)):
            raise ValueError('Use each variable name once.')
        tasks = [step.task for step in self.steps]
        if len(tasks) != len(set(tasks)):
            raise ValueError('Use each task at most once in a recipe.')
        return self


class ResourceCreate(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    kind: Literal['style', 'recipe']
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    content: dict = Field(default_factory=dict)
    note: str = Field(default='', max_length=2000)
    unsupported: dict = Field(default_factory=dict)


class ResourcePublish(ResourceCreate):
    expected_version_id: str


class ResourceArchive(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    archived: bool


class WritingPins(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    style: Choice = 'none'
    recipe: Choice = 'none'


class WritingChoices(Input):
    style: Choice = 'inherit'
    recipe: Choice = 'inherit'
    variables: dict[str, StrictStr | StrictFloat] = Field(default_factory=dict, max_length=20)


class ContentPreview(Input):
    content: dict
