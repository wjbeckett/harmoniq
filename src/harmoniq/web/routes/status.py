"""
Status API Routes
Provides system status and service connectivity endpoints.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import asyncio
import aiohttp
import logging
from datetime import datetime

from ... import config
from ...log_config import logger

router = APIRouter()


async def test_plex_connection() -> Dict[str, Any]:
    """Test connection to Plex server."""
    try:
        from ...plex_client import PlexClient

        plex_client = PlexClient()
        if plex_client and plex_client.plex:
            # Try to get server info
            server_info = plex_client.plex.account()
            return {
                "status": "connected",
                "server_name": getattr(plex_client.plex, "friendlyName", "Unknown"),
                "version": getattr(plex_client.plex, "version", "Unknown"),
                "last_checked": datetime.now().isoformat(),
            }
        else:
            return {
                "status": "disconnected",
                "error": "Failed to initialize Plex client",
                "last_checked": datetime.now().isoformat(),
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "last_checked": datetime.now().isoformat(),
        }


async def test_lastfm_connection() -> Dict[str, Any]:
    """Test connection to Last.fm API."""
    try:
        if not config.LASTFM_API_KEY or not config.LASTFM_USER:
            return {
                "status": "not_configured",
                "error": "Last.fm API key or username not configured",
                "last_checked": datetime.now().isoformat(),
            }

        from ...lastfm_client import LastfmClient

        lastfm_client = LastfmClient(config.LASTFM_API_KEY, config.LASTFM_USER)

        # Try to get user info (simple test)
        user_artists = lastfm_client.get_user_top_artists(period="1month", limit=1)

        if user_artists:
            return {
                "status": "connected",
                "username": config.LASTFM_USER,
                "test_result": f"Successfully fetched data for user",
                "last_checked": datetime.now().isoformat(),
            }
        else:
            return {
                "status": "error",
                "error": "Could not fetch user data from Last.fm",
                "last_checked": datetime.now().isoformat(),
            }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "last_checked": datetime.now().isoformat(),
        }


async def test_lidarr_connection() -> Dict[str, Any]:
    """Test connection to Lidarr API."""
    try:
        if not config.ENABLE_LIBRARY_GROWER:
            return {
                "status": "disabled",
                "message": "Library Grower is disabled",
                "last_checked": datetime.now().isoformat(),
            }

        if not config.LIDARR_URL or not config.LIDARR_API_KEY:
            return {
                "status": "not_configured",
                "error": "Lidarr URL or API key not configured",
                "last_checked": datetime.now().isoformat(),
            }

        from ...lidarr_client import LidarrClient

        lidarr_client = LidarrClient(config.LIDARR_URL, config.LIDARR_API_KEY)

        if lidarr_client.test_connection():
            return {
                "status": "connected",
                "url": config.LIDARR_URL,
                "test_result": "Connection successful",
                "last_checked": datetime.now().isoformat(),
            }
        else:
            return {
                "status": "error",
                "error": "Connection test failed",
                "last_checked": datetime.now().isoformat(),
            }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "last_checked": datetime.now().isoformat(),
        }


@router.get("/services")
async def get_service_status() -> Dict[str, Any]:
    """Get status of all connected services."""
    try:
        # Test all services concurrently
        plex_task = asyncio.create_task(test_plex_connection())
        lastfm_task = asyncio.create_task(test_lastfm_connection())
        lidarr_task = asyncio.create_task(test_lidarr_connection())

        # Wait for all tests to complete
        plex_status, lastfm_status, lidarr_status = await asyncio.gather(
            plex_task, lastfm_task, lidarr_task, return_exceptions=True
        )

        # Handle any exceptions
        if isinstance(plex_status, Exception):
            plex_status = {"status": "error", "error": str(plex_status)}
        if isinstance(lastfm_status, Exception):
            lastfm_status = {"status": "error", "error": str(lastfm_status)}
        if isinstance(lidarr_status, Exception):
            lidarr_status = {"status": "error", "error": str(lidarr_status)}

        return {
            "plex": plex_status,
            "lastfm": lastfm_status,
            "lidarr": lidarr_status,
            "overall_status": (
                "healthy"
                if all(
                    status.get("status") in ["connected", "disabled", "not_configured"]
                    for status in [plex_status, lastfm_status, lidarr_status]
                )
                else "degraded"
            ),
            "last_checked": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Service status check error: {e}")
        raise HTTPException(status_code=500, detail="Failed to check service status")


@router.get("/system")
async def get_system_status() -> Dict[str, Any]:
    """Get system status information."""
    try:
        return {
            "harmoniq_version": "1.0.0",  # TODO: Get from package
            "python_version": "3.11+",  # TODO: Get actual version
            "uptime": "Unknown",  # TODO: Calculate uptime
            "memory_usage": "Unknown",  # TODO: Get memory stats
            "config_status": {
                "harmoniq_flow_enabled": config.ENABLE_TIME_PLAYLIST,
                "library_grower_enabled": config.ENABLE_LIBRARY_GROWER,
                "scheduled_periods": (
                    len(config.SCHEDULED_PERIODS) if config.SCHEDULED_PERIODS else 0
                ),
                "plex_libraries": (
                    len(config.PLEX_MUSIC_LIBRARY_NAMES)
                    if config.PLEX_MUSIC_LIBRARY_NAMES
                    else 0
                ),
            },
            "last_checked": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"System status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get system status")


@router.post("/test-connection/{service}")
async def test_service_connection(service: str) -> Dict[str, Any]:
    """Test connection to a specific service on demand."""
    try:
        if service == "plex":
            return await test_plex_connection()
        elif service == "lastfm":
            return await test_lastfm_connection()
        elif service == "lidarr":
            return await test_lidarr_connection()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown service: {service}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service connection test error for {service}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to test {service} connection"
        )
