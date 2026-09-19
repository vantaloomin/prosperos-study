from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from server.profiles import Profiles, probe_key, profile_snapshot
from server.providers.config import ConnectionProbe, PrimaryUpdate, ProfileCreate, ProfileUpdate
from server.providers.service import ProviderService

router = APIRouter(prefix="/api/profiles")


class RestartedConnection(BaseModel):
    server_restarted: Literal[True]


def saved_profile(request, profile_id):
    with request.app.state.database.connect() as connection:
        return profile_snapshot(connection, profile_id)


@router.get('/{profile_id}/background-capability')
async def background_capability(profile_id: str, request: Request):
    return request.app.state.runner.provider.background_capability(saved_profile(request, profile_id))


@router.post('/{profile_id}/verify-background')
async def verify_background(profile_id: str, request: Request):
    return await request.app.state.runner.provider.verify_background(saved_profile(request, profile_id))


@router.post('/{profile_id}/reset-background')
async def reset_background(profile_id: str, body: RestartedConnection, request: Request):
    request.app.state.runner.provider.reset_background(saved_profile(request, profile_id))
    return {'reset': True}


def service(request: Request) -> Profiles:
    return Profiles(request.app.state.database, request.app.state.vault)


@router.get("")
def list_profiles(request: Request):
    return service(request).list()


@router.post("", status_code=201)
def create_profile(body: ProfileCreate, request: Request):
    return service(request).create(body)


@router.post('/discover')
async def discover_connection(body: ConnectionProbe, request: Request):
    key = probe_key(request.app.state.database, request.app.state.vault, body)
    provider = ProviderService(request.app.state.vault)
    adapter = provider.codex if body.config.provider == 'codex' else provider.http
    return await adapter.check(body.config.model_dump(), key)


@router.put("/primary")
def primary(body: PrimaryUpdate, request: Request):
    return service(request).primary(body.profile_id)


@router.put("/{profile_id}")
def update_profile(profile_id: str, body: ProfileUpdate, request: Request):
    return service(request).update(profile_id, body)


@router.post("/{profile_id}/check")
async def check_connection(profile_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        profile = profile_snapshot(connection, profile_id)
    return await ProviderService(request.app.state.vault).check(profile)
