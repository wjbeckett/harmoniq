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
from ..library_sync_manager import LibrarySyncManager  # New import
from ..plex_client import PlexClient  # New import
from ..lidarr_client import LidarrClient  # New import
from ..database import HarmoniqDatabase  # New import
from .. import config  # Import your config module

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
    sync_manager = LibrarySyncManager()
    app.state.sync_manager = sync_manager
    if sync_manager._initialized:
        logger.info(
            "Web app: Successfully attached to existing Library Sync Manager instance."
        )
    else:
        logger.error(
            "Web app: CRITICAL - Could not get an initialized Library Sync Manager. The scheduler may need to be running first."
        )

    # Get config directory
    config_dir = os.path.dirname(config.CONFIG_FILE_PATH)

    # Initialize other managers that are local to the web app
    try:
        database = HarmoniqDatabase(os.path.join(config_dir, "harmoniq.db"))
        app.state.database = database
        logger.info("Web app: Database handle created.")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize database handle: {e}")
        app.state.database = None

    try:
        recommendation_manager = AlbumRecommendationManager(config_dir)
        app.state.recommendation_manager = recommendation_manager
        logger.info("Web app: Recommendation manager initialized.")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize recommendation manager: {e}")
        app.state.recommendation_manager = None

    try:
        stats_tracker = StatsTracker(config_dir)
        app.state.stats_tracker = stats_tracker
        logger.info("Web app: Stats tracker initialized.")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize stats tracker: {e}")
        app.state.stats_tracker = None

    # Get the web directory path and mount static/templates (no change here)
    web_dir = Path(__file__).parent
    static_dir = web_dir / "static"
    templates_dir = web_dir / "templates"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    # Include API routes (no change here)
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
    app.include_router(status.router, prefix="/api/status", tags=["Status"])
    app.include_router(
        recommendations_api.router, prefix="/api", tags=["Recommendations"]
    )

    # Add API routes that use the sync_manager (no change to the functions themselves)
    @app.get("/api/sync/status")
    async def get_sync_status():
        if not app.state.sync_manager._initialized:
            return {"error": "Sync manager not available"}
        return app.state.sync_manager.get_sync_status()

    @app.post("/api/sync/force")
    async def force_sync():
        if not app.state.sync_manager._initialized:
            return {"error": "Sync manager not available"}
        return app.state.sync_manager.force_full_sync()

    @app.get("/api/sync/check/{mbid}")
    async def check_album_in_library(mbid: str):
        if not app.state.sync_manager._initialized:
            return {"error": "Sync manager not available"}
        return app.state.sync_manager.is_album_in_library(mbid)

    @app.get("/api/sync/check-by-name")
    async def check_album_by_name(artist: str, title: str):
        """
        Check if an album exists in any library by its artist and title.
        This is the primary endpoint for checking Last.fm recommendations.
        """
        if not app.state.sync_manager._initialized:
            return {"error": "Sync manager not available"}

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
