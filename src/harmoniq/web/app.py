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

    # Get config directory
    config_dir = os.path.dirname(config.CONFIG_FILE_PATH)

    # Initialize database
    try:
        database = HarmoniqDatabase(os.path.join(config_dir, "harmoniq.db"))
        app.state.database = database
        logger.info("Web app: Database initialized successfully")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize database: {e}")
        app.state.database = None

    # Initialize Plex client
    plex_client = None
    try:
        if config.PLEX_URL and config.PLEX_TOKEN:
            plex_client = PlexClient(baseurl=config.PLEX_URL, token=config.PLEX_TOKEN)
            if plex_client.connect():
                app.state.plex_client = plex_client
                logger.info("Web app: Plex client initialized successfully")
            else:
                logger.warning("Web app: Plex client connection failed")
                app.state.plex_client = None
        else:
            logger.warning("Web app: Plex configuration not found or incomplete")
            app.state.plex_client = None
    except Exception as e:
        logger.error(f"Web app: Failed to initialize Plex client: {e}")
        app.state.plex_client = None

    # Initialize Lidarr client
    lidarr_client = None
    try:
        if config.LIDARR_URL and config.LIDARR_API_KEY:
            lidarr_client = LidarrClient(
                base_url=config.LIDARR_URL, api_key=config.LIDARR_API_KEY
            )
            if lidarr_client.test_connection():
                app.state.lidarr_client = lidarr_client
                logger.info("Web app: Lidarr client initialized successfully")
            else:
                logger.warning("Web app: Lidarr client connection failed")
                app.state.lidarr_client = None
        else:
            logger.warning("Web app: Lidarr configuration not found or incomplete")
            app.state.lidarr_client = None
    except Exception as e:
        logger.error(f"Web app: Failed to initialize Lidarr client: {e}")
        app.state.lidarr_client = None

    # Initialize Library Sync Manager
    sync_manager = None
    if database and (plex_client or lidarr_client):
        try:
            sync_manager = LibrarySyncManager(plex_client, lidarr_client, database)
            app.state.sync_manager = sync_manager
            logger.info("Web app: Library Sync Manager initialized successfully")
        except Exception as e:
            logger.error(f"Web app: Failed to initialize Library Sync Manager: {e}")
            app.state.sync_manager = None
    else:
        logger.warning(
            "Web app: Cannot initialize sync manager - missing database or clients"
        )
        app.state.sync_manager = None

    # Initialize recommendation manager for web app
    try:
        recommendation_manager = AlbumRecommendationManager(config_dir)
        app.state.recommendation_manager = recommendation_manager
        logger.info("Web app: Recommendation manager initialized successfully")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize recommendation manager: {e}")
        app.state.recommendation_manager = None

    # Initialize stats tracker for web app
    stats_tracker = None
    try:
        stats_tracker = StatsTracker(config_dir)
        app.state.stats_tracker = stats_tracker
        logger.info("Web app: Stats tracker initialized successfully")
    except Exception as e:
        logger.error(f"Web app: Failed to initialize stats tracker: {e}")
        app.state.stats_tracker = None

    # Initialize discovery engine for web app
    try:
        # Pass the sync manager to the discovery engine
        discovery_engine = AlbumDiscoveryEngine(
            config, stats_tracker, sync_manager=sync_manager
        )
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

    # Add Library Sync API routes
    @app.get("/api/sync/status")
    async def get_sync_status():
        """Get current library sync status."""
        if not app.state.sync_manager:
            return {"error": "Sync manager not available"}

        return app.state.sync_manager.get_sync_status()

    @app.post("/api/sync/force")
    async def force_sync():
        """Force a full library sync."""
        if not app.state.sync_manager:
            return {"error": "Sync manager not available"}

        return app.state.sync_manager.force_full_sync()

    @app.get("/api/sync/check/{mbid}")
    async def check_album_in_library(mbid: str):
        """Check if an album exists in any library."""
        if not app.state.sync_manager:
            return {"error": "Sync manager not available"}

        return app.state.sync_manager.is_album_in_library(mbid)

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

    # Startup event
    @app.on_event("startup")
    async def startup_event():
        """Run startup tasks when the application starts."""
        logger.info("🚀 Harmoniq Web Application starting up...")

        # Perform library sync on startup
        if app.state.sync_manager:
            try:
                logger.info("Starting initial library sync...")
                sync_result = app.state.sync_manager.startup_sync()

                if sync_result["success"]:
                    logger.info(
                        f"✅ Startup sync completed: {sync_result.get('total_unique_albums', 0)} unique albums cached"
                    )

                    # Start background sync (every 6 hours)
                    app.state.sync_manager.start_background_sync(interval_hours=6)
                    logger.info("🔄 Background sync scheduled (every 6 hours)")
                else:
                    logger.error(
                        f"❌ Startup sync failed: {sync_result.get('error', 'Unknown error')}"
                    )
                    logger.info("Continuing without library cache...")

            except Exception as e:
                logger.error(f"❌ Startup sync error: {e}")
                logger.info("Continuing without library cache...")
        else:
            logger.warning("⚠️ Sync manager not available - skipping library sync")

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
