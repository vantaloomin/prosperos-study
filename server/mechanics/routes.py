from fastapi import APIRouter, Request

from server.mechanics.models import (
    PrepareBeat,
    RngUpdate,
    TableDefinition,
    TablePreview,
    TablePublish,
)
from server.mechanics.service import Mechanics
from server.mechanics.tables import Tables

router = APIRouter(prefix="/api")


@router.post("/roll-tables/validate")
def validate_table(body: TableDefinition):
    return body.model_dump()


@router.get("/roll-tables")
def tables(request: Request):
    return Tables(request.app.state.database).list()


@router.put("/roll-tables/{table_id}")
def publish_table(table_id: str, body: TablePublish, request: Request):
    return Tables(request.app.state.database).publish(table_id, body)


@router.get("/roll-tables/{table_id}/versions")
def table_history(table_id: str, request: Request):
    return Tables(request.app.state.database).history(table_id)


@router.post("/roll-tables/{table_id}/preview")
def preview(table_id: str, body: TablePreview, request: Request):
    return Mechanics(request.app.state.database).preview(table_id, body)


@router.get("/branches/{branch_id}/mechanics")
def branch_mechanics(branch_id: str, request: Request):
    return Mechanics(request.app.state.database).context(branch_id)


@router.put("/stories/{story_id}/randomness")
def settings(story_id: str, body: RngUpdate, request: Request):
    return Mechanics(request.app.state.database).configure(story_id, body)


@router.post("/branches/{branch_id}/opportunities", status_code=201)
def prepare(branch_id: str, body: PrepareBeat, request: Request):
    return Mechanics(request.app.state.database).prepare(branch_id, body)


@router.get("/opportunities/{opportunity_id}")
def opportunity(opportunity_id: str, request: Request):
    return Mechanics(request.app.state.database).detail(opportunity_id)
