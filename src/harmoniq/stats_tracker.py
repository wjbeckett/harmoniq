"""
Real-time statistics tracking for Harmoniq web dashboard.
Tracks actual system events and provides real data to the web UI.
Uses /app/config/ directory which is mapped to host appdata.
FIXED: Always reloads fresh data from disk for web API calls.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
from pathlib import Path


class HarmoniqStatsTracker:
    """Tracks real-time statistics for the Harmoniq system."""

    def __init__(self, stats_file: str = "/app/config/harmoniq_stats.json"):
        self.stats_file = stats_file
        self.lock = threading.Lock()
        self._ensure_config_dir()
        self.stats = self._load_stats()

    def _ensure_config_dir(self):
        """Ensure the config directory exists."""
        os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)

    def _load_stats(self) -> Dict:
        """Load stats from file or create default stats."""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load stats file: {e}")

        # Default stats structure
        return {
            "system_start_time": datetime.now().isoformat(),
            "last_restart_time": datetime.now().isoformat(),
            "total_playlist_updates": 0,
            "total_tracks_generated": 0,
            "total_period_switches": 0,
            "current_period": None,
            "last_update_time": None,
            "activity_log": [],
            "daily_stats": {},
        }

    def _reload_fresh_stats(self) -> Dict:
        """ALWAYS reload fresh stats from disk - for web API calls."""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not reload stats file: {e}")

        # Return cached stats if file read fails
        return self.stats

    def _save_stats(self):
        """Save stats to file."""
        try:
            with open(self.stats_file, "w") as f:
                json.dump(self.stats, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save stats: {e}")

    def record_system_start(self):
        """Record system startup."""
        with self.lock:
            self.stats["last_restart_time"] = datetime.now().isoformat()
            self._add_activity("System started", "system")
            self._save_stats()

    def record_playlist_update(self, period: str, track_count: int):
        """Record a playlist update."""
        with self.lock:
            self.stats["total_playlist_updates"] += 1
            self.stats["total_tracks_generated"] += track_count
            self.stats["last_update_time"] = datetime.now().isoformat()

            # Update daily stats
            today = datetime.now().strftime("%Y-%m-%d")
            if today not in self.stats["daily_stats"]:
                self.stats["daily_stats"][today] = {"updates": 0, "tracks": 0}
            self.stats["daily_stats"][today]["updates"] += 1
            self.stats["daily_stats"][today]["tracks"] += track_count

            self._add_activity(
                f"Updated {period} playlist ({track_count} tracks)", "playlist"
            )
            self._save_stats()

    def record_period_switch(self, new_period: str):
        """Record a period switch."""
        with self.lock:
            old_period = self.stats.get("current_period")
            if old_period != new_period:
                self.stats["current_period"] = new_period
                self.stats["total_period_switches"] += 1
                self._add_activity(f"Switched to {new_period} period", "period")
                self._save_stats()

    def record_library_grower_activity(self, albums_added: int, artists_processed: int):
        """Record Library Grower activity."""
        with self.lock:
            if "library_grower" not in self.stats:
                self.stats["library_grower"] = {"total_albums": 0, "total_artists": 0}

            self.stats["library_grower"]["total_albums"] += albums_added
            self.stats["library_grower"]["total_artists"] += artists_processed

            if albums_added > 0:
                self._add_activity(
                    f"Added {albums_added} new albums to Lidarr", "library"
                )
            self._save_stats()

    def record_activity(self, message: str, activity_type: str):
        """Public method to record custom activity."""
        with self.lock:
            self._add_activity(message, activity_type)
            self._save_stats()

    def _add_activity(self, message: str, activity_type: str):
        """Add an activity to the log."""
        activity = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "type": activity_type,
        }

        self.stats["activity_log"].insert(0, activity)  # Most recent first

        # Keep only last 50 activities
        if len(self.stats["activity_log"]) > 50:
            self.stats["activity_log"] = self.stats["activity_log"][:50]

    def get_system_uptime(self) -> Dict:
        """Get system uptime information with fresh data."""
        fresh_stats = self._reload_fresh_stats()  # ✅ Always reload

        try:
            start_time = datetime.fromisoformat(fresh_stats["system_start_time"])
            restart_time = datetime.fromisoformat(fresh_stats["last_restart_time"])
            now = datetime.now()

            total_uptime = now - start_time
            session_uptime = now - restart_time

            return {
                "total_days": total_uptime.days,
                "total_hours": int(total_uptime.total_seconds() // 3600),
                "session_days": session_uptime.days,
                "session_hours": int(session_uptime.total_seconds() // 3600),
                "start_time": start_time.isoformat(),
                "restart_time": restart_time.isoformat(),
            }
        except Exception:
            return {
                "total_days": 0,
                "total_hours": 0,
                "session_days": 0,
                "session_hours": 0,
            }

    def get_quick_stats(self) -> Dict:
        """Get quick stats for dashboard with FRESH data."""
        fresh_stats = self._reload_fresh_stats()  # ✅ Always reload
        uptime = self.get_system_uptime()

        return {
            "playlists_updated": fresh_stats.get("total_playlist_updates", 0),
            "tracks_generated": fresh_stats.get("total_tracks_generated", 0),
            "albums_discovered": fresh_stats.get("library_grower", {}).get(
                "total_albums", 0
            ),
            "artists_processed": fresh_stats.get("library_grower", {}).get(
                "total_artists", 0
            ),
            "days_online": max(uptime["total_days"], uptime["session_days"]),
            "period_switches": fresh_stats.get("total_period_switches", 0),
        }

    def get_recent_activity(self, limit: int = 10) -> List[Dict]:
        """Get recent activity for dashboard with FRESH data."""
        fresh_stats = self._reload_fresh_stats()  # ✅ Always reload
        activities = fresh_stats.get("activity_log", [])[:limit]

        # Add relative timestamps
        for activity in activities:
            try:
                timestamp = datetime.fromisoformat(activity["timestamp"])
                now = datetime.now()
                diff = now - timestamp

                if diff.days > 0:
                    activity["relative_time"] = (
                        f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
                    )
                elif diff.seconds > 3600:
                    hours = diff.seconds // 3600
                    activity["relative_time"] = (
                        f"{hours} hour{'s' if hours != 1 else ''} ago"
                    )
                elif diff.seconds > 60:
                    minutes = diff.seconds // 60
                    activity["relative_time"] = (
                        f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                    )
                else:
                    activity["relative_time"] = "Just now"
            except Exception:
                activity["relative_time"] = "Unknown"

        return activities

    def get_current_period_info(self) -> Dict:
        """Get current period information with FRESH data."""
        fresh_stats = self._reload_fresh_stats()  # ✅ Always reload

        return {
            "current_period": fresh_stats.get("current_period", "Unknown"),
            "last_update": fresh_stats.get("last_update_time"),
            "total_periods": 6,  # From your config
        }


# Global stats tracker instance
_stats_tracker = None


def get_stats_tracker() -> HarmoniqStatsTracker:
    """Get the global stats tracker instance."""
    global _stats_tracker
    if _stats_tracker is None:
        _stats_tracker = HarmoniqStatsTracker()
    return _stats_tracker
