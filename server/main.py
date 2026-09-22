from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from server.agent_templates import router as agent_template_router
from server.archives.routes import router as archive_router
from server.assessment.routes import router as assessment_router
from server.assessment.runner import AssessmentRunner
from server.authoring.routes import router as authoring_router
from server.authoring.runner import AuthoringRunner
from server.background.interpretation_routes import router as interpretation_router
from server.background.routes import router as background_router
from server.background.runner import BackgroundRunner
from server.backups.routes import router as backup_router
from server.backups.runner import BackupRunner
from server.backups.service import Backups
from server.branch_tools.routes import router as branch_tools_router
from server.cleanup.routes import router as cleanup_router
from server.database import Database
from server.errors import DomainError
from server.generation_routes import router as generation_router
from server.generation_runner import GenerationRunner
from server.inspiration.pack_routes import router as inspiration_pack_router
from server.inspiration.routes import router as inspiration_router
from server.library_formats.artwork_routes import router as artwork_router
from server.library_formats.import_routes import router as library_import_router
from server.library_formats.routes import router as library_source_router
from server.lore.routes import router as lore_router
from server.manuscript.routes import router as manuscript_router
from server.mechanics.routes import router as mechanics_router
from server.mechanics.tables import initialize_tables
from server.memory.control_routes import router as control_router
from server.memory.enrichment_routes import router as enrichment_router
from server.memory.maintenance_routes import router as maintenance_router
from server.memory.maintenance_runner import MaintenanceRunner
from server.memory.preparation_runner import PreparationRunner
from server.memory.readiness import router as readiness_router
from server.memory.relationship_routes import router as relationship_router
from server.memory.relationship_runner import RelationshipRunner
from server.memory.routes import router as memory_router
from server.memory.summary_routes import router as summary_router
from server.memory.summary_runner import SummaryRunner
from server.migration.batch_routes import router as migration_batch_router
from server.migration.preset_routes import router as preset_import_router
from server.migration.routes import router as migration_router
from server.phrases.routes import router as phrase_router
from server.profile_routes import router as profile_router
from server.prompts import initialize_prompts
from server.providers.vault import SystemVault
from server.reading_time_routes import router as reading_time_router
from server.routes import router
from server.scenes.routes import router as scene_router
from server.scenes.runner import SceneRunner
from server.side_routes import router as side_router
from server.side_runner import SideRunner
from server.text_edits.routes import router as text_edit_router
from server.transcripts import router as transcript_router
from server.workflow.routes import router as workflow_router
from server.workflow.runner import ReviewRunner
from server.writing.analysis_routes import router as style_analysis_router
from server.writing.analysis_runner import StyleAnalysisRunner
from server.writing.recipe_routes import router as recipe_router
from server.writing.recipe_runner import RecipeRunner
from server.writing.routes import router as writing_router


async def guard_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("x-roleplay-client") != "workspace":
            return JSONResponse({"detail": "Use the local workspace to make changes."}, status_code=403)
    return await call_next(request)


async def domain_error(_request: Request, error: DomainError):
    return JSONResponse({"detail": error.message}, status_code=error.status)


async def invalid_request(_request: Request, error: RequestValidationError):
    details = [{"loc": issue["loc"], "msg": issue["msg"], "type": issue["type"]}
               for issue in error.errors()]
    return JSONResponse({"detail": details}, status_code=422)


@asynccontextmanager
async def lifespan(app):
    app.state.summary_runner.recover()
    app.state.maintenance_runner.recover()
    app.state.relationship_runner.recover()
    app.state.authoring_runner.recover()
    app.state.style_analysis_runner.recover()
    app.state.recipe_runner.recover()
    app.state.background_runner.recover()
    app.state.assessment_runner.recover()
    app.state.runner.recover()
    app.state.side_runner.recover()
    app.state.review_runner.recover()
    app.state.scene_runner.recover()
    app.state.maintenance_runner.start()
    app.state.preparation_runner.start()
    app.state.relationship_runner.start()
    app.state.backup_runner.start()
    yield
    await app.state.backup_runner.shutdown()
    await app.state.preparation_runner.shutdown()
    await app.state.relationship_runner.shutdown()
    await app.state.maintenance_runner.shutdown()
    await app.state.assessment_runner.shutdown()
    await app.state.runner.shutdown()
    await app.state.side_runner.shutdown()
    await app.state.review_runner.shutdown()
    await app.state.scene_runner.shutdown()
    await app.state.background_runner.shutdown()
    await app.state.authoring_runner.shutdown()
    await app.state.style_analysis_runner.shutdown()
    await app.state.recipe_runner.shutdown()
    await app.state.summary_runner.shutdown()


def create_app(database_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="Roleplay workspace", version="0.9.0", lifespan=lifespan)
    app.state.database = Database(database_path)
    app.state.backups = Backups(app.state.database)
    app.state.backup_runner = BackupRunner(app.state.backups)
    app.state.vault = SystemVault()
    app.state.runner = GenerationRunner(app.state.database, app.state.vault)
    app.state.assessment_runner = AssessmentRunner(app.state.database, app.state.runner)
    app.state.side_runner = SideRunner(app.state.database, app.state.runner.provider)
    app.state.review_runner = ReviewRunner(app.state.database, app.state.runner.provider)
    app.state.scene_runner = SceneRunner(app.state.database, app.state.runner.provider)
    app.state.background_runner = BackgroundRunner(app.state.database, app.state.runner.provider)
    app.state.authoring_runner = AuthoringRunner(app.state.database, app.state.runner.provider)
    app.state.style_analysis_runner = StyleAnalysisRunner(app.state.database, app.state.runner.provider)
    app.state.recipe_runner = RecipeRunner(app.state.database, app.state.runner.provider)
    app.state.summary_runner = SummaryRunner(app.state.database, app.state.runner.provider)
    app.state.maintenance_runner = MaintenanceRunner(app.state.database, app.state.summary_runner)
    app.state.preparation_runner = PreparationRunner(app.state.database, app.state.runner.provider.scheduler)
    app.state.relationship_runner = RelationshipRunner(app.state.database, app.state.runner.provider)
    initialize_prompts(app.state.database)
    initialize_tables(app.state.database)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    app.middleware("http")(guard_writes)
    app.add_exception_handler(DomainError, domain_error)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(router)
    app.include_router(writing_router)
    app.include_router(style_analysis_router)
    app.include_router(recipe_router)
    app.include_router(branch_tools_router)
    app.include_router(text_edit_router)
    app.include_router(reading_time_router)
    app.include_router(agent_template_router)
    app.include_router(manuscript_router)
    app.include_router(authoring_router)
    app.include_router(library_source_router)
    app.include_router(library_import_router)
    app.include_router(migration_router)
    app.include_router(migration_batch_router)
    app.include_router(inspiration_router)
    app.include_router(inspiration_pack_router)
    app.include_router(preset_import_router)
    app.include_router(artwork_router)
    app.include_router(lore_router)
    app.include_router(memory_router)
    app.include_router(readiness_router)
    app.include_router(control_router)
    app.include_router(phrase_router)
    app.include_router(cleanup_router)
    app.include_router(enrichment_router)
    app.include_router(summary_router)
    app.include_router(maintenance_router)
    app.include_router(relationship_router)
    app.include_router(profile_router)
    app.include_router(generation_router)
    app.include_router(side_router)
    app.include_router(mechanics_router)
    app.include_router(workflow_router)
    app.include_router(scene_router)
    app.include_router(transcript_router)
    app.include_router(archive_router)
    app.include_router(backup_router)
    app.include_router(assessment_router)
    app.include_router(background_router)
    app.include_router(interpretation_router)
    frontend = Path(__file__).parent.parent / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
