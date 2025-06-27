"""
SQLite-based Album Recommendation Manager
Drop-in replacement for the JSON-based system with enhanced features
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .database import HarmoniqDatabase, RecommendationStatus

logger = logging.getLogger(__name__)


class AlbumRecommendationManager:
    """
    SQLite-based recommendation manager.
    Drop-in replacement for JSON-based system with same interface.
    """

    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.db_path = os.path.join(config_dir, "harmoniq.db")
        self.db = HarmoniqDatabase(self.db_path)

        # Legacy compatibility - these properties are accessed by existing code
        self.recommendations_file = self.db_path  # For debug endpoint

        logger.info(f"Initialized SQLite recommendation manager: {self.db_path}")

    def add_recommendation(self, album_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a new album recommendation.
        Returns recommendation ID if successful, None if duplicate.
        """
        try:
            rec_id = self.db.add_recommendation(album_data)
            logger.debug(f"Added recommendation: {album_data['artist']} - {album_data['title']}")
            return rec_id
        except Exception as e:
            logger.error(f"Error adding recommendation: {e}")
            return None

    def get_pending_recommendations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending recommendations for user review."""
        return self.db.get_recommendations_by_status(RecommendationStatus.PENDING, limit)

    def get_approved_recommendations(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get approved recommendations ready for processing."""
        return self.db.get_recommendations_by_status(RecommendationStatus.APPROVED, limit)

    def get_recommendations_by_status(self, status: Optional[RecommendationStatus] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recommendations filtered by status."""
        return self.db.get_recommendations_by_status(status, limit)

    def search_recommendations(self, query: str, status: Optional[RecommendationStatus] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Search recommendations by artist or title."""
        return self.db.search_recommendations(query, status, limit)

    def update_recommendation_status(self, rec_id: str, status: RecommendationStatus, user_notes: str = "", error_message: str = "") -> bool:
        """Update the status of a recommendation."""
        return self.db.update_recommendation_status(rec_id, status, user_notes, error_message)

    def bulk_update_status(self, rec_ids: List[str], status: RecommendationStatus, user_notes: str = "") -> Dict[str, bool]:
        """Update multiple recommendations at once."""
        return self.db.bulk_update_status(rec_ids, status, user_notes)

    def cleanup_old_recommendations(self, days_old: int = 30) -> int:
        """Clean up old denied/failed recommendations."""
        return self.db.cleanup_old_recommendations(days_old)

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive recommendation statistics."""
        return self.db.get_statistics()

    def get_album_cache(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all albums as a cache dictionary.
        Used by discovery engine for filtering duplicates.
        """
        # This method provides compatibility with existing filtering logic
        albums = {}

        # Get all albums from database
        with self.db._get_connection() as conn:
            rows = conn.execute("SELECT * FROM albums").fetchall()
            for row in rows:
                album_dict = self.db._row_to_album_dict(row)
                albums[row['id']] = album_dict

        return albums

    def refresh_album_cache(self):
        """
        Refresh album cache (no-op for SQLite version).
        Kept for compatibility with existing code.
        """
        pass

    # Legacy compatibility methods - these maintain the same interface as the JSON version
    @property
    def recommendations(self) -> Dict[str, Any]:
        """
        Legacy property for compatibility.
        Returns recommendations in the old JSON format structure.
        """
        all_recs = self.db.get_recommendations_by_status(limit=1000)

        # Convert to old format
        recommendations_dict = {}
        for rec in all_recs:
            recommendations_dict[rec['id']] = rec

        return {
            "recommendations": recommendations_dict,
            "last_updated": datetime.now().isoformat(),
            "total_count": len(recommendations_dict)
        }

    def save_recommendations(self):
        """
        Legacy method for compatibility.
        No-op for SQLite version as data is automatically persisted.
        """
        pass

    def load_recommendations(self):
        """
        Legacy method for compatibility.
        No-op for SQLite version as data is loaded from database.
        """
        pass


class StatsTracker:
    """
    SQLite-based statistics tracker.
    Drop-in replacement for JSON-based stats system.
    """

    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.db_path = os.path.join(config_dir, "harmoniq.db")
        self.db = HarmoniqDatabase(self.db_path)

        logger.info(f"Initialized SQLite stats tracker: {self.db_path}")

    def record_activity(self, message: str, activity_type: str = "general"):
        """Record an activity in the statistics."""
        self.db.record_activity(message, activity_type)

    def record_album_added(self, album_data: Dict[str, Any]):
        """Record when an album is successfully added to Lidarr."""
        self.db.record_album_added(album_data)

    def get_recent_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent activities for display."""
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT stat_data, timestamp FROM statistics 
                WHERE stat_type = 'activity'
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,)).fetchall()

            activities = []
            for row in rows:
                import json
                data = json.loads(row['stat_data'])
                data['timestamp'] = row['timestamp']
                activities.append(data)

            return activities

    def get_recently_added_albums(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently added albums for ribbon display."""
        return self.db.get_recently_added(limit)

    def get_discovery_run_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get history of discovery runs."""
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM discovery_runs 
                ORDER BY started_at DESC 
                LIMIT ?
            """, (limit,)).fetchall()

            return [dict(row) for row in rows]

    def get_user_action_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get history of user actions."""
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM user_actions 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,)).fetchall()

            return [dict(row) for row in rows]

    # Legacy compatibility methods
    def save_stats(self):
        """Legacy method - no-op for SQLite version."""
        pass

    def load_stats(self):
        """Legacy method - no-op for SQLite version."""
        pass

    @property
    def stats(self) -> Dict[str, Any]:
        """Legacy property for compatibility."""
        return {
            "activities": self.get_recent_activities(),
            "recently_added": self.get_recently_added_albums(),
            "discovery_runs": self.get_discovery_run_history(),
            "last_updated": datetime.now().isoformat()
        }
