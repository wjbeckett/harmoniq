"""
Dashboard API Routes
Provides data endpoints for the main dashboard.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime, timedelta
import logging

from ...main import get_active_period_details
from ... import config
from ...log_config import logger

router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview() -> Dict[str, Any]:
    """Get overview data for the main dashboard."""
    try:
        # Get current active period
        active_period = get_active_period_details()

        # Determine Harmoniq Flow status
        flow_status = {
            "enabled": config.ENABLE_TIME_PLAYLIST,
            "active_period": active_period.get("name") if active_period else None,
            "next_update": None,  # TODO: Calculate from scheduler
            "last_update": None,  # TODO: Get from logs or state
            "total_periods": (
                len(config.SCHEDULED_PERIODS) if config.SCHEDULED_PERIODS else 0
            ),
        }

        # Determine Library Grower status
        library_grower_status = {
            "enabled": config.ENABLE_LIBRARY_GROWER,
            "next_run": None,  # TODO: Calculate from scheduler
            "last_run": None,  # TODO: Get from logs or state
            "interval_hours": (
                config.LIBRARY_GROWER_RUN_INTERVAL_HOURS
                if config.ENABLE_LIBRARY_GROWER
                else None
            ),
            "albums_added_today": 0,  # TODO: Get from logs or database
            "total_albums_added": 0,  # TODO: Get from logs or database
        }

        # System status
        system_status = {
            "uptime": None,  # TODO: Calculate uptime
            "last_error": None,  # TODO: Get from logs
            "services_connected": {
                "plex": None,  # TODO: Test connection
                "lastfm": None,  # TODO: Test connection
                "lidarr": (
                    None if not config.ENABLE_LIBRARY_GROWER else None
                ),  # TODO: Test connection
            },
        }

        return {
            "harmoniq_flow": flow_status,
            "library_grower": library_grower_status,
            "system": system_status,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard overview")


@router.get("/recent-activity")
async def get_recent_activity(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent activity feed for the dashboard."""
    try:
        # TODO: Implement activity tracking
        # For now, return mock data
        mock_activities = [
            {
                "id": 1,
                "type": "library_grower",
                "message": "Added 3 new albums to Lidarr",
                "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
                "status": "success",
            },
            {
                "id": 2,
                "type": "harmoniq_flow",
                "message": "Updated Evening playlist (47 tracks)",
                "timestamp": (datetime.now() - timedelta(hours=6)).isoformat(),
                "status": "success",
            },
            {
                "id": 3,
                "type": "system",
                "message": "Harmoniq started successfully",
                "timestamp": (datetime.now() - timedelta(hours=12)).isoformat(),
                "status": "info",
            },
        ]

        return mock_activities[:limit]

    except Exception as e:
        logger.error(f"Recent activity error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent activity")


@router.get("/stats")
async def get_dashboard_stats() -> Dict[str, Any]:
    """Get statistics for dashboard widgets."""
    try:
        # TODO: Implement real statistics tracking
        # For now, return mock data
        stats = {
            "total_playlists_updated": 156,
            "total_albums_discovered": 89,
            "total_artists_processed": 234,
            "uptime_days": 15,
            "last_library_scan": (datetime.now() - timedelta(hours=3)).isoformat(),
            "active_periods_count": (
                len(config.SCHEDULED_PERIODS) if config.SCHEDULED_PERIODS else 0
            ),
        }

        return stats

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get dashboard statistics"
        )
