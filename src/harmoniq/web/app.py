"""
FastAPI Web Application for Harmoniq
Updated with template rendering, static file serving, and library sync management
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path
import logging

from .routes import dashboard, status, recommendations_api
from ..recommendation_manager import AlbumRecommendationManager, StatsTracker
from ..discovery_library_grower import AlbumDiscoveryEngine
from ..library_sync_manager import LibrarySyncManager
from ..plex_client import PlexClient
from ..lidarr_client import LidarrClient
from ..database import HarmoniqDatabase
from .. import config

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
    logger.info("🟢 Starting Harmoniq Web Application...")

    config_dir = os.path.dirname(config.CONFIG_FILE_PATH)
    database = HarmoniqDatabase(os.path.join(config_dir, "harmoniq.db"))
    lidarr_client = LidarrClient(config.LIDARR_URL, config.LIDARR_API_KEY)
    plex_client = PlexClient(config.PLEX_URL, config.PLEX_TOKEN)

    sync_manager = LibrarySyncManager(
        plex_client=plex_client, lidarr_client=lidarr_client, database=database
    )

    discovery_engine = AlbumDiscoveryEngine(config, sync_manager)

    recommendation_manager = AlbumRecommendationManager(config_dir)
    stats_tracker = StatsTracker(config_dir)

    app.state.database = database
    app.state.sync_manager = sync_manager
    app.state.discovery_engine = discovery_engine
    app.state.recommendation_manager = recommendation_manager
    app.state.stats_tracker = stats_tracker
    logger.info("✅ All web application services initialized successfully.")

    web_dir = Path(__file__).parent
    static_dir = web_dir / "static"
    templates_dir = web_dir / "templates"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
    app.include_router(status.router, prefix="/api/status", tags=["Status"])
    app.include_router(
        recommendations_api.router, prefix="/api", tags=["Recommendations"]
    )

    @app.get("/api/sync/status")
    async def get_sync_status():
        return app.state.sync_manager.get_sync_status()

    @app.post("/api/sync/force")
    async def force_sync():
        return app.state.sync_manager.force_full_sync()

    @app.get("/api/sync/check/{mbid}")
    async def check_album_in_library(mbid: str):
        return app.state.sync_manager.is_album_in_library(mbid)

    @app.get("/api/sync/check-by-name")
    async def check_album_by_name(artist: str, title: str):
        """
        Check if an album exists in any library by its artist and title.
        This is the primary endpoint for checking Last.fm recommendations.
        """
        return app.state.sync_manager.album_exists_by_name(artist=artist, title=title)

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
        return {"status": "healthy", "service": "harmoniq-web", "version": "1.0.0"}

    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up resources when the application shuts down."""
        logger.info("🛑 Harmoniq Web Application shutting down...")

        # Stop background sync
        if app.state.sync_manager:
            try:
                app.state.sync_manager.stop_background_sync()
                logger.info("✅ Background sync stopped")
            except Exception as e:
                logger.error(f"Error stopping background sync: {e}")

        logger.info("👋 Harmoniq Web Application shutdown complete")

    return app
