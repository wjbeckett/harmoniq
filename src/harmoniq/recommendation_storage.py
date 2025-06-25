
"""
Harmoniq Album Recommendations Storage System
Manages discovered albums awaiting user approval
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock
from enum import Enum

class RecommendationStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved" 
    DENIED = "denied"
    MAYBE = "maybe"
    PROCESSING = "processing"  # Being added to Lidarr
    ADDED = "added"  # Successfully added to Lidarr
    FAILED = "failed"  # Failed to add to Lidarr

class AlbumRecommendationManager:
    """Manages album recommendations and user decisions."""

    def __init__(self, config_dir: str = "/app/config"):
        self.config_dir = config_dir
        self.recommendations_file = os.path.join(config_dir, "album_recommendations.json")
        self.lock = Lock()
        self.recommendations = self._load_recommendations()

    def _load_recommendations(self) -> Dict[str, Any]:
        """Load recommendations from storage."""
        try:
            if os.path.exists(self.recommendations_file):
                with open(self.recommendations_file, 'r') as f:
                    data = json.load(f)
                    # Ensure required structure
                    if "recommendations" not in data:
                        data["recommendations"] = {}
                    if "metadata" not in data:
                        data["metadata"] = {
                            "last_discovery": None,
                            "total_discovered": 0,
                            "total_approved": 0,
                            "total_denied": 0,
                            "total_added": 0
                        }
                    return data
        except Exception as e:
            print(f"Error loading recommendations: {e}")

        # Return default structure
        return {
            "recommendations": {},
            "metadata": {
                "last_discovery": None,
                "total_discovered": 0,
                "total_approved": 0,
                "total_denied": 0,
                "total_added": 0
            }
        }

    def _save_recommendations(self):
        """Save recommendations to storage."""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.recommendations_file, 'w') as f:
                json.dump(self.recommendations, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving recommendations: {e}")

    def add_recommendation(self, album_data: Dict[str, Any]) -> str:
        """Add a new album recommendation."""
        with self.lock:
            # Generate unique ID (mbid preferred, fallback to hash)
            album_id = album_data.get("mbid") or f"album_{hash(f'{album_data.get('artist')}_{album_data.get('title')}')}_{int(datetime.now().timestamp())}"

            recommendation = {
                "id": album_id,
                "title": album_data.get("title", "Unknown Album"),
                "artist": album_data.get("artist", "Unknown Artist"),
                "year": album_data.get("year"),
                "mbid": album_data.get("mbid"),
                "lidarr_id": album_data.get("lidarr_id"),
                "status": RecommendationStatus.PENDING.value,
                "discovered_date": datetime.now().isoformat(),
                "source": album_data.get("source", "library_grower"),  # How it was discovered
                "similarity_score": album_data.get("similarity_score", 0.0),
                "related_artists": album_data.get("related_artists", []),
                "genres": album_data.get("genres", []),
                "tags": album_data.get("tags", []),
                "cover_art_url": album_data.get("cover_art_url"),
                "preview_url": album_data.get("preview_url"),
                "external_ratings": album_data.get("external_ratings", {}),  # LastFM, AllMusic, etc.
                "user_decision_date": None,
                "user_notes": "",
                "processing_attempts": 0,
                "last_error": None
            }

            # Don't add duplicates
            if album_id not in self.recommendations["recommendations"]:
                self.recommendations["recommendations"][album_id] = recommendation
                self.recommendations["metadata"]["total_discovered"] += 1
                self.recommendations["metadata"]["last_discovery"] = datetime.now().isoformat()
                self._save_recommendations()
                return album_id

            return album_id

    def update_recommendation_status(self, album_id: str, status: RecommendationStatus, 
                                   user_notes: str = "", error_message: str = None) -> bool:
        """Update the status of a recommendation."""
        with self.lock:
            if album_id not in self.recommendations["recommendations"]:
                return False

            old_status = self.recommendations["recommendations"][album_id]["status"]
            self.recommendations["recommendations"][album_id]["status"] = status.value
            self.recommendations["recommendations"][album_id]["user_decision_date"] = datetime.now().isoformat()

            if user_notes:
                self.recommendations["recommendations"][album_id]["user_notes"] = user_notes

            if error_message:
                self.recommendations["recommendations"][album_id]["last_error"] = error_message

            # Update metadata counters
            if old_status == RecommendationStatus.PENDING.value:
                if status == RecommendationStatus.APPROVED:
                    self.recommendations["metadata"]["total_approved"] += 1
                elif status == RecommendationStatus.DENIED:
                    self.recommendations["metadata"]["total_denied"] += 1

            if status == RecommendationStatus.ADDED:
                self.recommendations["metadata"]["total_added"] += 1

            self._save_recommendations()
            return True

    def get_recommendations_by_status(self, status: RecommendationStatus = None, 
                                    limit: int = None) -> List[Dict[str, Any]]:
        """Get recommendations filtered by status."""
        recommendations = list(self.recommendations["recommendations"].values())

        if status:
            recommendations = [r for r in recommendations if r["status"] == status.value]

        # Sort by discovery date (newest first)
        recommendations.sort(key=lambda x: x["discovered_date"], reverse=True)

        if limit:
            recommendations = recommendations[:limit]

        return recommendations

    def get_pending_recommendations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending recommendations for user review."""
        return self.get_recommendations_by_status(RecommendationStatus.PENDING, limit)

    def get_approved_recommendations(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get approved recommendations ready for processing."""
        return self.get_recommendations_by_status(RecommendationStatus.APPROVED, limit)

    def bulk_update_status(self, album_ids: List[str], status: RecommendationStatus, 
                          user_notes: str = "") -> Dict[str, bool]:
        """Update multiple recommendations at once."""
        results = {}
        for album_id in album_ids:
            results[album_id] = self.update_recommendation_status(album_id, status, user_notes)
        return results

    def cleanup_old_recommendations(self, days_old: int = 30):
        """Remove old denied/failed recommendations."""
        with self.lock:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            to_remove = []

            for album_id, rec in self.recommendations["recommendations"].items():
                if rec["status"] in [RecommendationStatus.DENIED.value, RecommendationStatus.FAILED.value]:
                    try:
                        rec_date = datetime.fromisoformat(rec["discovered_date"])
                        if rec_date < cutoff_date:
                            to_remove.append(album_id)
                    except Exception:
                        continue

            for album_id in to_remove:
                del self.recommendations["recommendations"][album_id]

            if to_remove:
                self._save_recommendations()

            return len(to_remove)

    def get_statistics(self) -> Dict[str, Any]:
        """Get recommendation statistics."""
        with self.lock:
            stats = self.recommendations["metadata"].copy()

            # Calculate current counts
            current_counts = {
                "pending": 0,
                "approved": 0,
                "denied": 0,
                "maybe": 0,
                "processing": 0,
                "added": 0,
                "failed": 0
            }

            for rec in self.recommendations["recommendations"].values():
                status = rec["status"]
                if status in current_counts:
                    current_counts[status] += 1

            stats.update(current_counts)
            return stats

    def search_recommendations(self, query: str, status: RecommendationStatus = None) -> List[Dict[str, Any]]:
        """Search recommendations by artist or album name."""
        query_lower = query.lower()
        results = []

        for rec in self.recommendations["recommendations"].values():
            if status and rec["status"] != status.value:
                continue

            if (query_lower in rec["title"].lower() or 
                query_lower in rec["artist"].lower()):
                results.append(rec)

        return sorted(results, key=lambda x: x["discovered_date"], reverse=True)
