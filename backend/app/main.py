from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api import api_router
from backend.app.adapters.oracle import initialize_oracle_client_runtime
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.core.telemetry import TelemetryMiddleware, setup_telemetry, shutdown_telemetry


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_telemetry(f"{settings.app_name}-api")
    init_db()
    initialize_oracle_client_runtime()
    yield
    shutdown_telemetry()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Oracle Migration App API",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(TelemetryMiddleware)
    app.include_router(api_router)
    return app


app = create_app()
