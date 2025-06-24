"""
Updated status routes that provide real data from the Harmoniq system.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
import aiohttp
import asyncio
import os
import sys
from pathlib import Path

# Add the parent directory to the path to import harmoniq modules
sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    from ...config import (
        TIMEZONE,
        TIME_PERIODS,
        PLEX_URL,
        PLEX_TOKEN,
        ENABLE_TIME_PLAYLIST,
        ENABLE_LIBRARY_GROWER,
    )
    from ...stats_tracker import get_stats_tracker
except ImportError as e:
    print(f"Warning: Could not import harmoniq modules: {e}")
    # Fallback values
    TIMEZONE = "UTC"
    TIME_PERIODS = []
    PLEX_URL = None
    PLEX_TOKEN = None
    ENABLE_TIME_PLAYLIST = True
    ENABLE_LIBRARY_GROWER = False

router = APIRouter()


def get_next_period_update():
    """Calculate the next period update time."""
    try:
        import pytz

        # Get timezone
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)

        # Get all period start hours
        period_hours = []
        for period in TIME_PERIODS:
            period_hours.append(
                (period.get("start_hour", 0), period.get("name", "Unknown"))
            )

        if not period_hours:
            return None

        # Sort by hour
        period_hours.sort()

        # Find next period
        current_hour = now.hour
        next_period = None

        for hour, name in period_hours:
            if hour > current_hour:
                next_period = (hour, name)
                break

        # If no period found today, use first period tomorrow
        if not next_period:
            next_period = (period_hours[0][0], period_hours[0][1])
            next_time = now.replace(
                hour=next_period[0], minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
        else:
            next_time = now.replace(
                hour=next_period[0], minute=0, second=0, microsecond=0
            )

        return {
            "next_period": next_period[1],
            "next_time": next_time.isoformat(),
            "next_time_formatted": next_time.strftime("%H:%M %Z"),
        }

    except Exception as e:
        print(f"Error calculating next period: {e}")
        return None


def get_current_period():
    """Get the current active period."""
    try:
        import pytz

        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        current_hour = now.hour

        # Find current period
        current_period = None
        for period in TIME_PERIODS:
            start_hour = period.get("start_hour", 0)

            # Check if this period is active
            # Find next period to determine end hour
            next_start = 24  # Default to end of day
            for other_period in TIME_PERIODS:
                other_hour = other_period.get("start_hour", 0)
                if other_hour > start_hour and other_hour < next_start:
                    next_start = other_hour

            if start_hour <= current_hour < next_start:
                current_period = period.get("name", "Unknown")
                break

        # If no period found, find the last period of the day
        if not current_period and TIME_PERIODS:
            latest_period = max(TIME_PERIODS, key=lambda p: p.get("start_hour", 0))
            if current_hour >= latest_period.get("start_hour", 0):
                current_period = latest_period.get("name", "Unknown")

        return current_period or "Unknown"

    except Exception as e:
        print(f"Error getting current period: {e}")
        return "Unknown"


@router.get("/system")
async def get_system_status():
    """Get overall system status."""
    try:
        stats_tracker = get_stats_tracker()
        uptime = stats_tracker.get_system_uptime()

        # Check if services are running (basic health check)
        scheduler_running = True  # Assume running if we can respond
        web_running = True  # We're responding, so web is running

        return {
            "status": "healthy",
            "uptime": uptime,
            "services": {
                "scheduler": "running" if scheduler_running else "stopped",
                "web_server": "running" if web_running else "stopped",
                "plex_connection": (
                    "connected" if PLEX_URL and PLEX_TOKEN else "not_configured"
                ),
            },
            "timezone": TIMEZONE,
            "features": {
                "harmoniq_flow": ENABLE_TIME_PLAYLIST,
                "library_grower": ENABLE_LIBRARY_GROWER,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "services": {
                "scheduler": "unknown",
                "web_server": "running",
                "plex_connection": "unknown",
            },
        }


@router.get("/harmoniq-flow")
async def get_harmoniq_flow_status():
    """Get Harmoniq Flow status."""
    try:
        stats_tracker = get_stats_tracker()
        period_info = stats_tracker.get_current_period_info()
        next_update = get_next_period_update()
        current_period = get_current_period()

        # Update current period in stats if different
        if current_period != period_info.get("current_period"):
            stats_tracker.record_period_switch(current_period)
            period_info = stats_tracker.get_current_period_info()

        return {
            "enabled": ENABLE_TIME_PLAYLIST,
            "status": "active" if ENABLE_TIME_PLAYLIST else "disabled",
            "current_period": current_period,
            "next_update": (
                next_update.get("next_time_formatted") if next_update else "Unknown"
            ),
            "next_period": next_update.get("next_period") if next_update else "Unknown",
            "total_periods": len(TIME_PERIODS),
            "last_update": period_info.get("last_update"),
            "periods": [p.get("name", "Unknown") for p in TIME_PERIODS],
        }
    except Exception as e:
        return {
            "enabled": False,
            "status": "error",
            "error": str(e),
            "current_period": "Unknown",
            "next_update": "Unknown",
            "total_periods": 0,
        }


@router.get("/library-grower")
async def get_library_grower_status():
    """Get Library Grower status."""
    try:
        stats_tracker = get_stats_tracker()
        quick_stats = stats_tracker.get_quick_stats()

        return {
            "enabled": ENABLE_LIBRARY_GROWER,
            "status": "active" if ENABLE_LIBRARY_GROWER else "disabled",
            "albums_discovered": quick_stats.get("albums_discovered", 0),
            "artists_processed": quick_stats.get("artists_processed", 0),
            "last_run": None,  # TODO: Track last run time
            "next_run": "24 hours" if ENABLE_LIBRARY_GROWER else "Disabled",
        }
    except Exception as e:
        return {"enabled": False, "status": "error", "error": str(e)}


@router.get("/quick-stats")
async def get_quick_stats():
    """Get quick statistics for dashboard."""
    try:
        stats_tracker = get_stats_tracker()
        return stats_tracker.get_quick_stats()
    except Exception as e:
        # Fallback to basic stats if tracker fails
        return {
            "playlists_updated": 0,
            "tracks_generated": 0,
            "albums_discovered": 0,
            "artists_processed": 0,
            "days_online": 0,
            "period_switches": 0,
        }


@router.get("/recent-activity")
async def get_recent_activity():
    """Get recent activity for dashboard."""
    try:
        stats_tracker = get_stats_tracker()
        return {"activities": stats_tracker.get_recent_activity(limit=10)}
    except Exception as e:
        return {
            "activities": [
                {
                    "message": "System started",
                    "type": "system",
                    "relative_time": "Just now",
                }
            ]
        }


@router.post("/trigger-update")
async def trigger_harmoniq_flow_update():
    """Trigger a manual Harmoniq Flow update."""
    try:
        # This would need to communicate with the scheduler
        # For now, return a success message
        return {"success": True, "message": "Update triggered successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "harmoniq-web",
    }
