from pydantic import Field

from server.models import Input


class SceneSelection(Input):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    branch_id: str
    head_id: str
    from_node_id: str
    through_node_id: str


class Chapter(Input):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    scenes: list[SceneSelection] = Field(default_factory=list, max_length=500)


class Bookmark(Input):
    id: str = Field(min_length=1, max_length=100)
    scene_id: str
    node_id: str
    label: str = Field(min_length=1, max_length=200)


class ManuscriptDocument(Input):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default='', max_length=200)
    language: str = Field(default='en', pattern=r'^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{1,8})*$')
    include_contributions: bool = True
    scene_headings: bool = False
    chapters: list[Chapter] = Field(default_factory=list, max_length=500)
    bookmarks: list[Bookmark] = Field(default_factory=list, max_length=2000)


class ManuscriptUpdate(Input):
    expected_revision: int = Field(ge=0)
    document: ManuscriptDocument


class PublicationCreate(Input):
    expected_revision: int = Field(ge=0)
