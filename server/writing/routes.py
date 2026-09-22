from fastapi import APIRouter, Request

from server.writing.bundle_export import export_bundle
from server.writing.bundle_models import BundleExport, BundleImport, BundlePreview
from server.writing.bundles import import_bundle, prepare_bundle
from server.writing.editor_options import recipe_editor_options
from server.writing.models import (
    ContentPreview,
    ResourceArchive,
    ResourceCreate,
    ResourcePublish,
    WritingChoices,
    WritingPins,
)
from server.writing.pins import read_pins, save_pins
from server.writing.recipe_models import RecipeRunPreview
from server.writing.recipe_plan import prepare_recipe, recipe_preview
from server.writing.resolution import resolve
from server.writing.resources import Resources, parse_content, validate_links, version
from server.writing.starters import STARTERS

router = APIRouter(prefix='/api')


@router.post('/writing-versions/{version_id}/export')
def export_resource(version_id: str, body: BundleExport, request: Request):
    with request.app.state.database.connect() as connection:
        return export_bundle(connection, version_id, body.include_samples)


@router.post('/writing-bundles/preview')
def preview_bundle(body: BundlePreview, request: Request):
    with request.app.state.database.connect() as connection:
        return prepare_bundle(connection, body)[0]


@router.post('/writing-bundles/import', status_code=201)
def import_resources(body: BundleImport, request: Request):
    return import_bundle(request.app.state.database, body)


@router.get('/writing-starters')
def starters():
    return [{**item, 'content': parse_content('recipe', item['content'])} for item in STARTERS]


@router.post('/writing-recipes/validate')
def validate_recipe(body: ContentPreview, request: Request):
    content = parse_content('recipe', body.content)
    with request.app.state.database.connect() as connection:
        validate_links(connection, 'recipe', content)
    return content


@router.get('/writing-recipes/options')
def recipe_options():
    return recipe_editor_options()


@router.post('/branches/{branch_id}/writing-recipes/preview')
def preview_recipe_run(branch_id: str, body: RecipeRunPreview, request: Request):
    with request.app.state.database.connect() as connection:
        return recipe_preview(prepare_recipe(connection, branch_id, body))


@router.get('/writing-resources')
def list_resources(request: Request, include_archived: bool = False):
    return Resources(request.app.state.database).list(include_archived)


@router.post('/writing-resources', status_code=201)
def create_resource(body: ResourceCreate, request: Request):
    return Resources(request.app.state.database).create(body)


@router.get('/writing-resources/{asset_id}/versions')
def history(asset_id: str, request: Request):
    return Resources(request.app.state.database).history(asset_id)


@router.post('/writing-resources/{asset_id}/versions', status_code=201)
def publish(asset_id: str, body: ResourcePublish, request: Request):
    return Resources(request.app.state.database).publish(asset_id, body)


@router.put('/writing-resources/{asset_id}/archive')
def archive(asset_id: str, body: ResourceArchive, request: Request):
    return Resources(request.app.state.database).archive(asset_id, body)


@router.get('/writing-versions/{version_id}')
def get_version(version_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return version(connection, version_id)


@router.get('/stories/{story_id}/writing-preferences')
def preferences(story_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return read_pins(connection, story_id)


@router.put('/stories/{story_id}/writing-preferences')
def update_preferences(story_id: str, body: WritingPins, request: Request):
    return save_pins(request.app.state.database, story_id, body)


@router.post('/stories/{story_id}/writing-preview')
def preview(story_id: str, body: WritingChoices, request: Request):
    with request.app.state.database.connect() as connection:
        return resolve(connection, story_id, body)
