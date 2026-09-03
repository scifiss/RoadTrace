from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import Settings
from app.service import AnalysisService
from app.storage.sqlite import AnalysisStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = AnalysisStore(settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.initialize()
        app.state.analysis_store = store
        app.state.analysis_service = AnalysisService(settings, store)
        yield

    app = FastAPI(
        title="RoadTrace API",
        version="0.1.0",
        description="Evidence-backed reverse roadmaps from statically analyzed repositories",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()
