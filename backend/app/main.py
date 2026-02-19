import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics.router import router as analytics_router
from app.auth.router import router as auth_router
from app.companies.router import router as companies_router
from app.config import settings
from app.monitoring.router import router as monitoring_router
from app.signals.router import router as signals_router
from app.software.router import router as software_router
from app.outreach.router import router as outreach_router
from app.portal.router import router as portal_router
from app.intelligence.router import router as intelligence_router
from app.demo.router import router as demo_router
from app.integrations.router import router as integrations_router
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.logging import RequestLoggingMiddleware

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.integrations.sync_scheduler import drive_sync_loop, gmail_sync_loop, jira_poll_sync_loop

    gmail_task = asyncio.create_task(gmail_sync_loop())
    drive_task = asyncio.create_task(drive_sync_loop())
    jira_poll_task = asyncio.create_task(jira_poll_sync_loop())
    yield
    gmail_task.cancel()
    drive_task.cancel()
    jira_poll_task.cancel()
    for task in [gmail_task, drive_task, jira_poll_task]:
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vendor Integration Intelligence Platform",
        version="0.1.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(companies_router, prefix="/api/v1")
    app.include_router(monitoring_router, prefix="/api/v1")
    app.include_router(software_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(portal_router, prefix="/api/v1")
    app.include_router(outreach_router, prefix="/api/v1")
    app.include_router(intelligence_router, prefix="/api/v1")
    app.include_router(demo_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Serve the built frontend in production (when frontend/dist exists)
    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            """SPA fallback — serve index.html for all non-API routes."""
            target = frontend_dist / full_path
            if full_path and target.is_file() and str(target.resolve()).startswith(str(frontend_dist.resolve())):
                return FileResponse(str(target))
            return FileResponse(str(frontend_dist / "index.html"))

    return app


app = create_app()
