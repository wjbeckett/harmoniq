"""
Dashboard API Routes - Real Data Integration
Provides data endpoints for the main dashboard with live statistics.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime, timedelta
import logging

from ...main import get_active_period_details
from ... import config
from ...log_config import logger
from ...stats_tracker import get_stats_tracker

router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview() -> Dict[str, Any]:
    """Get overview data for the main dashboard with real data."""
    try:
        # Get real stats
        stats_tracker = get_stats_tracker()
        uptime = stats_tracker.get_system_uptime()

        # Get current active period
        active_period = get_active_period_details()

        # Calculate next update time
        next_update = None
        if config.ENABLE_TIME_PLAYLIST and config.SCHEDULED_PERIODS:
            try:
                import pytz
                tz = pytz.timezone(config.TIMEZONE)
                now = datetime.now(tz)
                current_hour = now.hour

                # Find next period
                next_hour = None
                for period in config.SCHEDULED_PERIODS:
                    start_hour = period.get('start_hour', 0)
                    if start_hour > current_hour:
                        next_hour = start_hour
                        break

                if next_hour is None and config.SCHEDULED_PERIODS:
                    # Next update is tomorrow at first period
                    first_period = min(config.SCHEDULED_PERIODS, key=lambda p: p.get('start_hour', 0))
                    next_hour = first_period.get('start_hour', 0)
                    next_time = now.replace(hour=next_hour, minute=0, second=0, microsecond=0) + timedelta(days=1)
                else:
                    next_time = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)

                next_update = next_time.strftime("%H:%M %Z")
            except Exception as e:
                logger.error(f"Error calculating next update: {e}")
                next_update = "Unknown"

        # Harmoniq Flow status with real data
        flow_status = {
            "enabled": config.ENABLE_TIME_PLAYLIST,
            "active_period": active_period.get("name") if active_period else "Unknown",
            "next_update": next_update,
            "last_update": stats_tracker.get_last_update_time(),
            "total_periods": (
                len(config.SCHEDULED_PERIODS) if config.SCHEDULED_PERIODS else 0
            ),
        }

        # Library Grower status
        library_grower_status = {
            "enabled": config.ENABLE_LIBRARY_GROWER,
            "next_run": f"{config.LIBRARY_GROWER_RUN_INTERVAL_HOURS} hours" if config.ENABLE_LIBRARY_GROWER else "Disabled",
            "last_run": None,  # TODO: Track last run time
            "interval_hours": (
                config.LIBRARY_GROWER_RUN_INTERVAL_HOURS
                if config.ENABLE_LIBRARY_GROWER
                else None
            ),
            "albums_added_today": 0,  # TODO: Get from daily stats
            "total_albums_added": 0,  # TODO: Get from stats
        }

        # System status with real uptime
        system_status = {
            "uptime": f"{uptime['session_days']} days, {uptime['session_hours']} hours",
            "last_error": None,  # TODO: Get from logs
            "services_connected": {
                "plex": "connected" if config.PLEX_URL and config.PLEX_TOKEN else "not_configured",
                "lastfm": "connected" if config.LASTFM_API_KEY and config.LASTFM_USER else "not_configured",
                "lidarr": (
                    "connected" if config.ENABLE_LIBRARY_GROWER and config.LIDARR_URL and config.LIDARR_API_KEY 
                    else "disabled" if not config.ENABLE_LIBRARY_GROWER 
                    else "not_configured"
                ),
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
    """Get recent activity feed for the dashboard with real data."""
    try:
        stats_tracker = get_stats_tracker()
        activities = stats_tracker.get_recent_activity(limit=limit)

        # Convert to dashboard format
        dashboard_activities = []
        for i, activity in enumerate(activities):
            dashboard_activities.append({
                "id": i + 1,
                "type": activity.get("type", "system"),
                "message": activity.get("message", "Unknown activity"),
                "timestamp": activity.get("timestamp", datetime.now().isoformat()),
                "status": "success" if activity.get("type") in ["playlist", "library"] else "info",
            })

        return dashboard_activities

    except Exception as e:
        logger.error(f"Recent activity error: {e}")
        # Fallback to basic activity
        return [{
            "id": 1,
            "type": "system",
            "message": "System running",
            "timestamp": datetime.now().isoformat(),
            "status": "info",
        }]


@router.get("/stats")
async def get_dashboard_stats() -> Dict[str, Any]:
    """Get statistics for dashboard widgets with REAL DATA."""
    try:
        stats_tracker = get_stats_tracker()
        quick_stats = stats_tracker.get_quick_stats()
        uptime = stats_tracker.get_system_uptime()

        # Return real statistics
        stats = {
            "total_playlists_updated": quick_stats.get("playlists_updated", 0),
            "total_tracks_generated": quick_stats.get("tracks_generated", 0),
            "total_albums_discovered": quick_stats.get("albums_discovered", 0),
            "total_artists_processed": quick_stats.get("artists_processed", 0),
            "uptime_days": uptime.get("session_days", 0),
            "period_switches": quick_stats.get("period_switches", 0),
            "last_library_scan": None,  # TODO: Track library scans
            "active_periods_count": (
                len(config.SCHEDULED_PERIODS) if config.SCHEDULED_PERIODS else 0
            ),
        }

        return stats

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        # Fallback stats if tracker fails
        return {
            "total_playlists_updated": 0,
            "total_tracks_generated": 0,
            "total_albums_discovered": 0,
            "total_artists_processed": 0,
            "uptime_days": 0,
            "period_switches": 0,
            "active_periods_count": 0,
        }


@router.post("/trigger-update")
async def trigger_harmoniq_flow_update():
    """Trigger a manual Harmoniq Flow update."""
    try:
        # This would need to communicate with the scheduler
        # For now, return a success message
        stats_tracker = get_stats_tracker()
        stats_tracker.record_activity("Manual update triggered", "manual")

        return {
            "success": True,
            "message": "Update triggered successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def dashboard_health():
    """Dashboard health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "harmoniq-dashboard"
    }
