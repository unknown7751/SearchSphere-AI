"""FastAPI application factory.  Run with:  uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, evaluation, health, index_admin, search, workbench
from app.core.config import Settings, settings as default_settings
from app.core.errors import register_error_handlers
from app.database.connection import connect
from app.database.schema import init_db
from app.services.search_engine import SearchEngine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = connect(settings.database_path)
        try:
            init_db(conn)
            engine = SearchEngine(wildcard_limit=settings.wildcard_expansion_limit)
            engine.rebuild(conn)  # the database is the source of truth; the index is derived from it
        finally:
            conn.close()
        app.state.engine = engine
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Information-retrieval backend: Boolean, tolerant (prefix/wildcard) and TF-IDF/cosine search, "
            "query expansion, Rocchio relevance feedback, evaluation metrics and document ingestion."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api")
    for module in (health, documents, search, workbench, evaluation, index_admin):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
