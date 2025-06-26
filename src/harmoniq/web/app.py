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

from .routes import dashboard, status, recommendations_api
from ..recommendation_storage import AlbumRecommendationManager
from ..discovery_library_grower import AlbumDiscoveryEngine
import logging

# Configure logging
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Harmoniq Web Dashboard",
        description="Intelligent Music Library Management Dashboard",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Initialize recommendation manager for web app
    try:
        from .. import config  # Import your config

        recommendation_manager = AlbumRecommendationManager()
        app.state.recommendation_manager = recommendation_manager
        logger.info("Web app: Recommendation manager initialized successfully")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize recommendation manager: {e}")
        app.state.recommendation_manager = None

    # Initialize discovery engine for web app
    try:
        from ..lastfm_client import LastfmClient
        from ..lidarr_client import LidarrClient
        from .. import config  # Import your config

        lastfm_client = LastfmClient(
            api_key=config.LASTFM_API_KEY, api_user=config.LASTFM_USERNAME
        )
        lidarr_client = LidarrClient(
            base_url=config.LIDARR_URL, api_key=config.LIDARR_API_KEY
        )
        discovery_engine = AlbumDiscoveryEngine(config, lastfm_client, lidarr_client)
        app.state.discovery_engine = discovery_engine
        logger.info("Web app: Discovery engine initialized successfully")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize discovery engine: {e}")
        app.state.discovery_engine = None

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
    app.include_router(
        recommendations_api.router, prefix="/api", tags=["Recommendations"]
    )

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

    @app.get("/recommendations", response_class=HTMLResponse)
    async def recommendations_page(request: Request):
        """Album recommendations page."""
        return templates.TemplateResponse(
            "recommendations.html",
            {"request": request, "page_title": "Recommendations - Harmoniq"},
        )

    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "harmoniq-web", "version": "1.0.0"}

    return app
