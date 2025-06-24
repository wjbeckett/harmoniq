"""
FastAPI Web Application for Harmoniq
Updated with template rendering and static file serving
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path

from .routes import dashboard, status


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Harmoniq Web Dashboard",
        description="Intelligent Music Library Management Dashboard",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Get the web directory path
    web_dir = Path(__file__).parent
    static_dir = web_dir / "static"
    templates_dir = web_dir / "templates"

    # Mount static files
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Setup Jinja2 templates
    templates = Jinja2Templates(directory=str(templates_dir))

    # Include API routes with /api prefix
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
    app.include_router(status.router, prefix="/api/status", tags=["Status"])

    # HTML Routes (Dashboard Pages)
    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        """Main dashboard page."""
        return templates.TemplateResponse(
            "dashboard.html", {"request": request, "page_title": "Dashboard - Harmoniq"}
        )

    @app.get("/config", response_class=HTMLResponse)
    async def config_page(request: Request):
        """Configuration page (placeholder for future)."""
        return templates.TemplateResponse(
            "base.html", {"request": request, "page_title": "Configuration - Harmoniq"}
        )

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        """Logs page (placeholder for future)."""
        return templates.TemplateResponse(
            "base.html", {"request": request, "page_title": "Logs - Harmoniq"}
        )

    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "harmoniq-web", "version": "1.0.0"}

    return app
