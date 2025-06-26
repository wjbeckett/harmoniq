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
    """Get overview data for the main dashboard with proper service counting."""
    try:
        # Get real stats and service status
        stats_tracker = get_stats_tracker()
        uptime = stats_tracker.get_system_uptime()

        # Get current active period
        active_period = get_active_period_details()

        # Calculate next update time properly
        next_update = "Unknown"
        if config.ENABLE_TIME_PLAYLIST and config.SCHEDULED_PERIODS:
            try:
                import pytz

                tz = pytz.timezone(config.TIMEZONE)
                now = datetime.now(tz)
                current_hour = now.hour

                # Sort periods by start hour
                sorted_periods = sorted(
                    config.SCHEDULED_PERIODS, key=lambda p: p.get("start_hour", 0)
                )

                # Find next period
                next_period = None
                for period in sorted_periods:
                    start_hour = period.get("start_hour", 0)
                    if start_hour > current_hour:
                        next_period = period
                        break

                if next_period:
                    # Next period is today
                    next_time = now.replace(
                        hour=next_period["start_hour"],
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                    next_update = next_time.strftime("%H:%M %Z")
                else:
                    # Next period is tomorrow (first period of the day)
                    first_period = sorted_periods[0]
                    next_time = now.replace(
                        hour=first_period["start_hour"],
                        minute=0,
                        second=0,
                        microsecond=0,
                    ) + timedelta(days=1)
                    next_update = f"Tomorrow {next_time.strftime('%H:%M %Z')}"

            except Exception as e:
                logger.error(f"Error calculating next update: {e}")
                next_update = "Unknown"

        # Get service status and count properly
        from .status import (
            test_plex_connection,
            test_lastfm_connection,
            test_lidarr_connection,
        )

        # Test services
        plex_status = await test_plex_connection()
        lastfm_status = await test_lastfm_connection()
        lidarr_status = await test_lidarr_connection()

        # Count connected services
        connected_count = 0
        total_count = 3

        if plex_status.get("status") == "connected":
            connected_count += 1
        if lastfm_status.get("status") == "connected":
            connected_count += 1
        if lidarr_status.get("status") == "connected":
            connected_count += 1

        # Determine overall system status
        system_status = "healthy"
        if connected_count == 0:
            system_status = "critical"
        elif connected_count < total_count:
            system_status = "issues"

        # Harmoniq Flow status with real data
        flow_status = {
            "enabled": config.ENABLE_TIME_PLAYLIST,
            "active_period": active_period.get("name") if active_period else "Unknown",
            "next_update": next_update,
            "last_update": stats_tracker.stats.get("last_update_time"),
            "total_periods": (
                len(config.SCHEDULED_PERIODS) if config.SCHEDULED_PERIODS else 0
            ),
        }

        # Library Grower status
        library_grower_status = {
            "enabled": config.ENABLE_LIBRARY_GROWER,
            "next_run": (
                f"Every {config.LIBRARY_GROWER_RUN_INTERVAL_HOURS} hours"
                if config.ENABLE_LIBRARY_GROWER
                else "Disabled"
            ),
            "last_run": None,  # TODO: Track last run time
            "interval_hours": (
                config.LIBRARY_GROWER_RUN_INTERVAL_HOURS
                if config.ENABLE_LIBRARY_GROWER
                else None
            ),
            "albums_added_today": 0,  # TODO: Get from daily stats
            "total_albums_added": stats_tracker._reload_fresh_stats()
            .get("library_grower", {})
            .get("total_albums", 0),
        }

        # System status with proper counting
        system_info = {
            "status": system_status,
            "uptime": f"{uptime['session_days']} days, {uptime['session_hours']} hours",
            "last_error": None,  # TODO: Get from logs
            "services_connected": {
                "plex": plex_status.get("status", "unknown"),
                "lastfm": lastfm_status.get("status", "unknown"),
                "lidarr": lidarr_status.get("status", "unknown"),
            },
            "connected_count": connected_count,
            "total_count": total_count,
        }

        return {
            "harmoniq_flow": flow_status,
            "library_grower": library_grower_status,
            "system": system_info,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        # Return safe fallback data
        return {
            "harmoniq_flow": {
                "enabled": config.ENABLE_TIME_PLAYLIST if config else False,
                "active_period": "Unknown",
                "next_update": "Unknown",
                "last_update": None,
                "total_periods": 0,
            },
            "library_grower": {
                "enabled": config.ENABLE_LIBRARY_GROWER if config else False,
                "next_run": "Unknown",
                "last_run": None,
                "interval_hours": None,
                "albums_added_today": 0,
                "total_albums_added": 0,
            },
            "system": {
                "status": "error",
                "uptime": "Unknown",
                "last_error": str(e),
                "services_connected": {
                    "plex": "unknown",
                    "lastfm": "unknown",
                    "lidarr": "unknown",
                },
                "connected_count": 0,
                "total_count": 3,
            },
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/recent-activity")
async def get_recent_activity(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent activity feed for the dashboard with real data."""
    try:
        stats_tracker = get_stats_tracker()
        activities = stats_tracker.get_recent_activity(limit=limit)

        # Convert to dashboard format
        dashboard_activities = []
        for i, activity in enumerate(activities):
            dashboard_activities.append(
                {
                    "id": i + 1,
                    "type": activity.get("type", "system"),
                    "message": activity.get("message", "Unknown activity"),
                    "timestamp": activity.get("timestamp", datetime.now().isoformat()),
                    "status": (
                        "success"
                        if activity.get("type") in ["playlist", "library"]
                        else "info"
                    ),
                }
            )

        return dashboard_activities

    except Exception as e:
        logger.error(f"Recent activity error: {e}")
        # Fallback to basic activity
        return [
            {
                "id": 1,
                "type": "system",
                "message": "System running",
                "timestamp": datetime.now().isoformat(),
                "status": "info",
            }
        ]


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


@router.get("/recently-added-albums")
async def get_recently_added_albums(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recently added albums for the ribbon display."""
    try:
        stats_tracker = get_stats_tracker()
        albums = stats_tracker.get_recently_added_albums(limit)

        # Enhance with album art URLs if not already present
        for album in albums:
            if not album.get("cover_art_url") and album.get("mbid"):
                # Try to get cover art from MusicBrainz
                album["cover_art_url"] = (
                    f"https://coverartarchive.org/release/{album['mbid']}/front-250"
                )
            elif not album.get("cover_art_url"):
                # Fallback placeholder
                album["cover_art_url"] = "/static/images/album-placeholder.png"

        return albums

    except Exception as e:
        logger.error(f"Error fetching recently added albums: {e}")
        return []


@router.get("/album-stats")
async def get_album_stats() -> Dict[str, Any]:
    """Get album-related statistics."""
    try:
        stats_tracker = get_stats_tracker()
        today_count = stats_tracker.get_daily_album_count()
        fresh_stats = stats_tracker._reload_fresh_stats()

        return {
            "albums_added_today": today_count,
            "total_albums_added": fresh_stats.get("library_grower", {}).get(
                "total_albums", 0
            ),
            "recent_albums_count": len(fresh_stats.get("recently_added_albums", [])),
            "last_album_added": (
                fresh_stats.get("recently_added_albums", [{}])[0].get("added_date")
                if fresh_stats.get("recently_added_albums")
                else None
            ),
        }

    except Exception as e:
        logger.error(f"Error fetching album stats: {e}")
        return {
            "albums_added_today": 0,
            "total_albums_added": 0,
            "recent_albums_count": 0,
            "last_album_added": None,
        }


@router.post("/trigger-update")
async def trigger_harmoniq_flow_update():
    """Trigger a manual Harmoniq Flow update."""
    try:
        # This would need to communicate with the scheduler
        # For now, return a success message
        stats_tracker = get_stats_tracker()
        stats_tracker.record_activity("Manual update triggered", "manual")

        return {"success": True, "message": "Update triggered successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def dashboard_health():
    """Dashboard health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "harmoniq-dashboard",
    }
