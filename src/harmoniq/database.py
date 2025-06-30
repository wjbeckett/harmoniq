"""
SQLite Database System for Harmoniq
Handles albums, recommendations, discovery runs, user actions, statistics, and library caching
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from enum import Enum
import os

logger = logging.getLogger(__name__)


class LibrarySyncStatus(Enum):
    """Status values for library sync operations."""

    STARTED = "started"
    SUCCESS = "success"
    PARTIAL = "partial"  # Some libraries failed
    FAILED = "failed"


class RecommendationStatus(Enum):
    """Status enum for album recommendations."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    PROCESSING = "processing"
    ADDED = "added"
    FAILED = "failed"


class LibrarySyncStatus(Enum):
    """Status enum for library sync operations."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


class HarmoniqDatabase:
    """Thread-safe SQLite database for Harmoniq."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_database()

    def _init_database(self):
        """Initialize database with all required tables."""
        with self._get_connection() as conn:
            # Albums table - cache of all known albums
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS albums (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    year INTEGER,
                    mbid TEXT,
                    type TEXT DEFAULT 'studio',
                    source TEXT,
                    cover_art_url TEXT,
                    external_ratings TEXT, -- JSON
                    tags TEXT, -- JSON array
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Recommendations table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY,
                    album_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    similarity_score REAL DEFAULT 0.0,
                    user_notes TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (album_id) REFERENCES albums (id)
                )
            """
            )

            # Discovery runs table - track discovery cycles
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovery_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    albums_discovered INTEGER DEFAULT 0,
                    new_recommendations INTEGER DEFAULT 0,
                    artists_processed INTEGER DEFAULT 0,
                    similar_artists_found INTEGER DEFAULT 0,
                    albums_filtered INTEGER DEFAULT 0,
                    errors TEXT, -- JSON array
                    status TEXT DEFAULT 'running'
                )
            """
            )

            # User actions table - track all user interactions
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL, -- 'status_change', 'bulk_update', 'cleanup', etc.
                    recommendation_id TEXT,
                    old_status TEXT,
                    new_status TEXT,
                    user_notes TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT -- JSON for additional data
                )
            """
            )

            # Statistics table - replace JSON stats file
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_type TEXT NOT NULL, -- 'activity', 'album_added', 'discovery_run', etc.
                    stat_data TEXT NOT NULL, -- JSON data
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Recently added albums (for ribbon display)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recently_added (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    album_id TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (album_id) REFERENCES albums (id)
                )
            """
            )

            # NEW: Lidarr library cache
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lidarr_albums (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lidarr_id INTEGER UNIQUE NOT NULL,
                    artist_name TEXT NOT NULL,
                    album_title TEXT NOT NULL,
                    artist_mbid TEXT,
                    album_mbid TEXT,
                    status TEXT, -- 'wanted', 'downloaded', 'missing', etc.
                    monitored BOOLEAN DEFAULT 1,
                    quality_profile_id INTEGER,
                    release_date TEXT,
                    path TEXT,
                    size_on_disk INTEGER DEFAULT 0,
                    date_added TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    raw_data TEXT -- JSON of full Lidarr response
                )
            """
            )

            # NEW: Plex library cache
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plex_albums (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plex_id TEXT UNIQUE NOT NULL,
                    artist_name TEXT NOT NULL,
                    album_title TEXT NOT NULL,
                    year INTEGER,
                    rating_key TEXT,
                    guid TEXT,
                    thumb TEXT,
                    art TEXT,
                    duration INTEGER,
                    track_count INTEGER,
                    date_added TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    library_section_id INTEGER,
                    raw_data TEXT -- JSON of full Plex response
                )
            """
            )

            # NEW: Library sync history
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_syncs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_type TEXT NOT NULL, -- 'lidarr', 'plex', 'both'
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT NOT NULL, -- 'success', 'partial', 'failed', 'in_progress'
                    albums_synced INTEGER DEFAULT 0,
                    albums_added INTEGER DEFAULT 0,
                    albums_updated INTEGER DEFAULT 0,
                    albums_removed INTEGER DEFAULT 0,
                    errors TEXT, -- JSON array
                    sync_duration_seconds REAL,
                    details TEXT -- JSON for additional sync info
                )
            """
            )

            # Create indexes for better performance
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations (status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recommendations_discovered ON recommendations (discovered_date)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums (artist)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_albums_title ON albums (title)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_actions_timestamp ON user_actions (timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_statistics_type ON statistics (stat_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recently_added_timestamp ON recently_added (added_at)"
            )

            # NEW: Library cache indexes for fast filtering
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lidarr_artist_album ON lidarr_albums (artist_name, album_title)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lidarr_status ON lidarr_albums (status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lidarr_updated ON lidarr_albums (last_updated)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_plex_artist_album ON plex_albums (artist_name, album_title)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_plex_updated ON plex_albums (last_updated)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_library_syncs_type ON library_syncs (sync_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_library_syncs_started ON library_syncs (started_at)"
            )

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get a thread-safe database connection."""
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def add_album(self, album_data: Dict[str, Any]) -> str:
        """Add or update an album in the database."""
        album_id = f"{album_data['artist']}_{album_data['title']}".replace(
            " ", "_"
        ).lower()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO albums 
                (id, title, artist, year, mbid, type, source, cover_art_url, external_ratings, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    album_id,
                    album_data["title"],
                    album_data["artist"],
                    album_data.get("year"),
                    album_data.get("mbid"),
                    album_data.get("type", "studio"),
                    album_data.get("source"),
                    album_data.get("cover_art_url"),
                    json.dumps(album_data.get("external_ratings", {})),
                    json.dumps(album_data.get("tags", [])),
                ),
            )
            conn.commit()

        return album_id

    def get_album(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Get an album by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM albums WHERE id = ?", (album_id,)
            ).fetchone()
            if row:
                return self._row_to_album_dict(row)
        return None

    def search_albums(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search albums by artist or title."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM albums 
                WHERE artist LIKE ? OR title LIKE ?
                ORDER BY artist, title
                LIMIT ?
            """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()

            return [self._row_to_album_dict(row) for row in rows]

    def add_recommendation(self, album_data: Dict[str, Any]) -> str:
        """Add a new recommendation."""
        # First add/update the album
        album_id = self.add_album(album_data)

        # Create recommendation ID
        rec_id = f"rec_{album_id}_{int(datetime.now().timestamp())}"

        with self._get_connection() as conn:
            # Check if recommendation already exists for this album
            existing = conn.execute(
                """
                SELECT id FROM recommendations 
                WHERE album_id = ? AND status IN ('pending', 'approved')
            """,
                (album_id,),
            ).fetchone()

            if existing:
                logger.debug(f"Recommendation already exists for album {album_id}")
                return existing["id"]

            # Add new recommendation
            conn.execute(
                """
                INSERT INTO recommendations 
                (id, album_id, similarity_score, discovered_date)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (rec_id, album_id, album_data.get("similarity_score", 0.8)),
            )
            conn.commit()

        return rec_id

    def get_recommendations_by_status(
        self, status: Optional[RecommendationStatus] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recommendations by status."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT r.*, a.* FROM recommendations r
                    JOIN albums a ON r.album_id = a.id
                    WHERE r.status = ?
                    ORDER BY r.discovered_date DESC
                    LIMIT ?
                """,
                    (status.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT r.*, a.* FROM recommendations r
                    JOIN albums a ON r.album_id = a.id
                    ORDER BY r.discovered_date DESC
                    LIMIT ?
                """,
                    (limit,),
                ).fetchall()

            return [self._row_to_recommendation_dict(row) for row in rows]

    def search_recommendations(
        self, query: str, status: Optional[RecommendationStatus] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search recommendations by artist or title."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT r.*, a.* FROM recommendations r
                    JOIN albums a ON r.album_id = a.id
                    WHERE (a.artist LIKE ? OR a.title LIKE ?) AND r.status = ?
                    ORDER BY r.discovered_date DESC
                    LIMIT ?
                """,
                    (f"%{query}%", f"%{query}%", status.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT r.*, a.* FROM recommendations r
                    JOIN albums a ON r.album_id = a.id
                    WHERE a.artist LIKE ? OR a.title LIKE ?
                    ORDER BY r.discovered_date DESC
                    LIMIT ?
                """,
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()

            return [self._row_to_recommendation_dict(row) for row in rows]

    def update_recommendation_status(
        self,
        rec_id: str,
        status: RecommendationStatus,
        user_notes: str = "",
        error_message: str = "",
    ) -> bool:
        """Update recommendation status."""
        with self._get_connection() as conn:
            # Get current status for logging
            current = conn.execute(
                "SELECT status FROM recommendations WHERE id = ?", (rec_id,)
            ).fetchone()
            if not current:
                return False

            old_status = current["status"]

            # Update recommendation
            conn.execute(
                """
                UPDATE recommendations 
                SET status = ?, user_notes = ?, error_message = ?, status_updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (status.value, user_notes, error_message, rec_id),
            )

            # Log user action
            conn.execute(
                """
                INSERT INTO user_actions (action_type, recommendation_id, old_status, new_status, user_notes)
                VALUES ('status_change', ?, ?, ?, ?)
            """,
                (rec_id, old_status, status.value, user_notes),
            )

            conn.commit()

        return True

    def bulk_update_status(
        self, rec_ids: List[str], status: RecommendationStatus, user_notes: str = ""
    ) -> Dict[str, bool]:
        """Bulk update recommendation statuses."""
        results = {}

        with self._get_connection() as conn:
            for rec_id in rec_ids:
                try:
                    # Get current status
                    current = conn.execute(
                        "SELECT status FROM recommendations WHERE id = ?", (rec_id,)
                    ).fetchone()
                    if not current:
                        results[rec_id] = False
                        continue

                    old_status = current["status"]

                    # Update recommendation
                    conn.execute(
                        """
                        UPDATE recommendations 
                        SET status = ?, user_notes = ?, status_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (status.value, user_notes, rec_id),
                    )

                    # Log user action
                    conn.execute(
                        """
                        INSERT INTO user_actions (action_type, recommendation_id, old_status, new_status, user_notes)
                        VALUES ('bulk_update', ?, ?, ?, ?)
                    """,
                        (rec_id, old_status, status.value, user_notes),
                    )

                    results[rec_id] = True

                except Exception as e:
                    logger.error(f"Error updating recommendation {rec_id}: {e}")
                    results[rec_id] = False

            conn.commit()

        return results

    def cleanup_old_recommendations(self, days_old: int = 30) -> int:
        """Clean up old denied/failed recommendations."""
        cutoff_date = datetime.now() - timedelta(days=days_old)

        with self._get_connection() as conn:
            # Get count first
            count = conn.execute(
                """
                SELECT COUNT(*) as count FROM recommendations 
                WHERE status IN ('denied', 'failed') AND discovered_date < ?
            """,
                (cutoff_date,),
            ).fetchone()["count"]

            # Delete old recommendations
            conn.execute(
                """
                DELETE FROM recommendations 
                WHERE status IN ('denied', 'failed') AND discovered_date < ?
            """,
                (cutoff_date,),
            )

            # Log cleanup action
            conn.execute(
                """
                INSERT INTO user_actions (action_type, user_notes, details)
                VALUES ('cleanup', ?, ?)
            """,
                (
                    f"Cleaned up {count} recommendations older than {days_old} days",
                    json.dumps({"days_old": days_old, "count": count}),
                ),
            )

            conn.commit()

        return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive recommendation statistics."""
        with self._get_connection() as conn:
            # Basic counts by status
            status_counts = {}
            for status in RecommendationStatus:
                count = conn.execute(
                    """
                    SELECT COUNT(*) as count FROM recommendations WHERE status = ?
                """,
                    (status.value,),
                ).fetchone()["count"]
                status_counts[status.value] = count

            # Total albums in database
            total_albums = conn.execute(
                "SELECT COUNT(*) as count FROM albums"
            ).fetchone()["count"]

            # Recent activity (last 7 days)
            week_ago = datetime.now() - timedelta(days=7)
            recent_discoveries = conn.execute(
                """
                SELECT COUNT(*) as count FROM recommendations WHERE discovered_date > ?
            """,
                (week_ago,),
            ).fetchone()["count"]

            recent_actions = conn.execute(
                """
                SELECT COUNT(*) as count FROM user_actions WHERE timestamp > ?
            """,
                (week_ago,),
            ).fetchone()["count"]

            # Discovery run stats
            last_run = conn.execute(
                """
                SELECT * FROM discovery_runs ORDER BY started_at DESC LIMIT 1
            """
            ).fetchone()

            # Library stats
            lidarr_count = conn.execute(
                "SELECT COUNT(*) as count FROM lidarr_albums"
            ).fetchone()["count"]
            plex_count = conn.execute(
                "SELECT COUNT(*) as count FROM plex_albums"
            ).fetchone()["count"]

            # Calculate derived stats
            total_decisions = status_counts.get("approved", 0) + status_counts.get(
                "denied", 0
            )
            approval_rate = (
                (status_counts.get("approved", 0) / total_decisions * 100)
                if total_decisions > 0
                else 0
            )

            return {
                **status_counts,
                "total_albums": total_albums,
                "total_recommendations": sum(status_counts.values()),
                "total_decisions": total_decisions,
                "approval_rate": round(approval_rate, 1),
                "pending_count": status_counts.get("pending", 0),
                "ready_to_process": status_counts.get("approved", 0),
                "recent_discoveries_7d": recent_discoveries,
                "recent_actions_7d": recent_actions,
                "last_discovery_run": dict(last_run) if last_run else None,
                "lidarr_albums_cached": lidarr_count,
                "plex_albums_cached": plex_count,
            }

    def start_discovery_run(self) -> int:
        """Start a new discovery run and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO discovery_runs (started_at, status) 
                VALUES (CURRENT_TIMESTAMP, 'running')
            """
            )
            run_id = cursor.lastrowid
            conn.commit()

        return run_id

    def update_discovery_run(self, run_id: int, results: Dict[str, Any]):
        """Update discovery run with results."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE discovery_runs 
                SET completed_at = CURRENT_TIMESTAMP,
                    albums_discovered = ?,
                    new_recommendations = ?,
                    artists_processed = ?,
                    similar_artists_found = ?,
                    albums_filtered = ?,
                    errors = ?,
                    status = 'completed'
                WHERE id = ?
            """,
                (
                    results.get("albums_discovered", 0),
                    results.get("new_recommendations", 0),
                    results.get("artists_processed", 0),
                    results.get("similar_artists_found", 0),
                    results.get("albums_filtered", 0),
                    json.dumps(results.get("errors", [])),
                    run_id,
                ),
            )
            conn.commit()

    def record_activity(self, message: str, activity_type: str = "general"):
        """Record activity in statistics table."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO statistics (stat_type, stat_data)
                VALUES ('activity', ?)
            """,
                (
                    json.dumps(
                        {
                            "message": message,
                            "type": activity_type,
                            "timestamp": datetime.now().isoformat(),
                        }
                    ),
                ),
            )
            conn.commit()

    def record_album_added(self, album_data: Dict[str, Any]):
        """Record when an album is added to Lidarr."""
        album_id = f"{album_data['artist']}_{album_data['title']}".replace(
            " ", "_"
        ).lower()

        with self._get_connection() as conn:
            # Add to recently added
            conn.execute(
                """
                INSERT INTO recently_added (album_id) VALUES (?)
            """,
                (album_id,),
            )

            # Record in statistics
            conn.execute(
                """
                INSERT INTO statistics (stat_type, stat_data)
                VALUES ('album_added', ?)
            """,
                (
                    json.dumps(
                        {
                            "album_id": album_id,
                            "artist": album_data["artist"],
                            "title": album_data["title"],
                            "timestamp": datetime.now().isoformat(),
                        }
                    ),
                ),
            )

            conn.commit()

    def get_recently_added(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently added albums for ribbon display."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT ra.added_at, a.* FROM recently_added ra
                JOIN albums a ON ra.album_id = a.id
                ORDER BY ra.added_at DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()

            return [self._row_to_album_dict(row) for row in rows]

    # NEW: Library Sync Methods

    def start_library_sync(self, sync_type: str) -> int:
        """Start a new library sync operation."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO library_syncs (sync_type, status) 
                VALUES (?, 'in_progress')
            """,
                (sync_type,),
            )
            sync_id = cursor.lastrowid
            conn.commit()

        return sync_id

    def complete_library_sync(
        self, sync_id: int, status: LibrarySyncStatus, results: Dict[str, Any]
    ):
        """Complete a library sync operation with results."""
        sync_duration = (
            datetime.now()
            - datetime.fromisoformat(
                results.get("started_at", datetime.now().isoformat())
            )
        ).total_seconds()

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE library_syncs 
                SET completed_at = CURRENT_TIMESTAMP,
                    status = ?,
                    albums_synced = ?,
                    albums_added = ?,
                    albums_updated = ?,
                    albums_removed = ?,
                    errors = ?,
                    sync_duration_seconds = ?,
                    details = ?
                WHERE id = ?
            """,
                (
                    status.value,
                    results.get("albums_synced", 0),
                    results.get("albums_added", 0),
                    results.get("albums_updated", 0),
                    results.get("albums_removed", 0),
                    json.dumps(results.get("errors", [])),
                    sync_duration,
                    json.dumps(results.get("details", {})),
                    sync_id,
                ),
            )
            conn.commit()

    def sync_lidarr_albums(self, albums: List[Dict[str, Any]]) -> Dict[str, int]:
        """Sync Lidarr albums to database cache."""
        stats = {"added": 0, "updated": 0, "total": len(albums)}

        with self._get_connection() as conn:
            for album in albums:
                try:
                    # Check if album exists
                    existing = conn.execute(
                        """
                        SELECT id FROM lidarr_albums WHERE lidarr_id = ?
                    """,
                        (album["id"],),
                    ).fetchone()

                    if existing:
                        # Update existing album
                        conn.execute(
                            """
                            UPDATE lidarr_albums 
                            SET artist_name = ?, album_title = ?, artist_mbid = ?, album_mbid = ?,
                                status = ?, monitored = ?, quality_profile_id = ?, release_date = ?,
                                path = ?, size_on_disk = ?, date_added = ?, last_updated = CURRENT_TIMESTAMP,
                                raw_data = ?
                            WHERE lidarr_id = ?
                        """,
                            (
                                album.get("artist", {}).get("artistName", ""),
                                album.get("title", ""),
                                album.get("artist", {}).get("foreignArtistId"),
                                album.get("foreignAlbumId"),
                                album.get("status", ""),
                                album.get("monitored", True),
                                album.get("qualityProfileId"),
                                album.get("releaseDate"),
                                album.get("path", ""),
                                album.get("sizeOnDisk", 0),
                                album.get("dateAdded"),
                                json.dumps(album),
                                album["id"],
                            ),
                        )
                        stats["updated"] += 1
                    else:
                        # Insert new album
                        conn.execute(
                            """
                            INSERT INTO lidarr_albums 
                            (lidarr_id, artist_name, album_title, artist_mbid, album_mbid,
                             status, monitored, quality_profile_id, release_date, path,
                             size_on_disk, date_added, raw_data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                album["id"],
                                album.get("artist", {}).get("artistName", ""),
                                album.get("title", ""),
                                album.get("artist", {}).get("foreignArtistId"),
                                album.get("foreignAlbumId"),
                                album.get("status", ""),
                                album.get("monitored", True),
                                album.get("qualityProfileId"),
                                album.get("releaseDate"),
                                album.get("path", ""),
                                album.get("sizeOnDisk", 0),
                                album.get("dateAdded"),
                                json.dumps(album),
                            ),
                        )
                        stats["added"] += 1

                except Exception as e:
                    logger.error(
                        f"Error syncing Lidarr album {album.get('id', 'unknown')}: {e}"
                    )

            conn.commit()

        return stats

    def sync_plex_albums(self, albums: List[Dict[str, Any]]) -> Dict[str, int]:
        """Sync Plex albums to database cache."""
        stats = {"added": 0, "updated": 0, "total": len(albums)}

        with self._get_connection() as conn:
            for album in albums:
                try:
                    # Check if album exists
                    existing = conn.execute(
                        """
                        SELECT id FROM plex_albums WHERE plex_id = ?
                    """,
                        (album["ratingKey"],),
                    ).fetchone()

                    if existing:
                        # Update existing album
                        conn.execute(
                            """
                            UPDATE plex_albums 
                            SET artist_name = ?, album_title = ?, year = ?, rating_key = ?,
                                guid = ?, thumb = ?, art = ?, duration = ?, track_count = ?,
                                date_added = ?, library_section_id = ?, last_updated = CURRENT_TIMESTAMP,
                                raw_data = ?
                            WHERE plex_id = ?
                        """,
                            (
                                album.get("parentTitle", ""),
                                album.get("title", ""),
                                album.get("year"),
                                album.get("ratingKey"),
                                album.get("guid"),
                                album.get("thumb"),
                                album.get("art"),
                                album.get("duration"),
                                album.get("leafCount"),
                                album.get("addedAt"),
                                album.get("librarySectionID"),
                                json.dumps(album),
                                album["ratingKey"],
                            ),
                        )
                        stats["updated"] += 1
                    else:
                        # Insert new album
                        conn.execute(
                            """
                            INSERT INTO plex_albums 
                            (plex_id, artist_name, album_title, year, rating_key, guid,
                             thumb, art, duration, track_count, date_added, library_section_id, raw_data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                album["ratingKey"],
                                album.get("parentTitle", ""),
                                album.get("title", ""),
                                album.get("year"),
                                album.get("ratingKey"),
                                album.get("guid"),
                                album.get("thumb"),
                                album.get("art"),
                                album.get("duration"),
                                album.get("leafCount"),
                                album.get("addedAt"),
                                album.get("librarySectionID"),
                                json.dumps(album),
                            ),
                        )
                        stats["added"] += 1

                except Exception as e:
                    logger.error(
                        f"Error syncing Plex album {album.get('ratingKey', 'unknown')}: {e}"
                    )

            conn.commit()

        return stats

    def is_album_in_lidarr(self, artist: str, title: str) -> bool:
        """Check if album exists in Lidarr library cache."""
        with self._get_connection() as conn:
            result = conn.execute(
                """
                SELECT 1 FROM lidarr_albums 
                WHERE LOWER(artist_name) = LOWER(?) AND LOWER(album_title) = LOWER(?)
                LIMIT 1
            """,
                (artist, title),
            ).fetchone()

            return result is not None

    def is_album_in_plex(self, artist: str, title: str) -> bool:
        """Check if album exists in Plex library cache."""
        with self._get_connection() as conn:
            result = conn.execute(
                """
                SELECT 1 FROM plex_albums 
                WHERE LOWER(artist_name) = LOWER(?) AND LOWER(album_title) = LOWER(?)
                LIMIT 1
            """,
                (artist, title),
            ).fetchone()

            return result is not None

    def is_album_in_library(self, artist: str, title: str) -> Dict[str, bool]:
        """Check if album exists in either Lidarr or Plex libraries."""
        return {
            "in_lidarr": self.is_album_in_lidarr(artist, title),
            "in_plex": self.is_album_in_plex(artist, title),
            "in_any_library": self.is_album_in_lidarr(artist, title)
            or self.is_album_in_plex(artist, title),
        }

    def get_library_stats(self) -> Dict[str, Any]:
        """Get comprehensive library statistics."""
        with self._get_connection() as conn:
            # Lidarr stats
            lidarr_total = conn.execute(
                "SELECT COUNT(*) as count FROM lidarr_albums"
            ).fetchone()["count"]
            lidarr_monitored = conn.execute(
                "SELECT COUNT(*) as count FROM lidarr_albums WHERE monitored = 1"
            ).fetchone()["count"]
            lidarr_downloaded = conn.execute(
                "SELECT COUNT(*) as count FROM lidarr_albums WHERE status = 'downloaded'"
            ).fetchone()["count"]

            # Plex stats
            plex_total = conn.execute(
                "SELECT COUNT(*) as count FROM plex_albums"
            ).fetchone()["count"]

            # Recent sync info
            last_lidarr_sync = conn.execute(
                """
                SELECT * FROM library_syncs 
                WHERE sync_type IN ('lidarr', 'both') 
                ORDER BY started_at DESC LIMIT 1
            """
            ).fetchone()

            last_plex_sync = conn.execute(
                """
                SELECT * FROM library_syncs 
                WHERE sync_type IN ('plex', 'both') 
                ORDER BY started_at DESC LIMIT 1
            """
            ).fetchone()

            return {
                "lidarr": {
                    "total_albums": lidarr_total,
                    "monitored_albums": lidarr_monitored,
                    "downloaded_albums": lidarr_downloaded,
                    "last_sync": dict(last_lidarr_sync) if last_lidarr_sync else None,
                },
                "plex": {
                    "total_albums": plex_total,
                    "last_sync": dict(last_plex_sync) if last_plex_sync else None,
                },
                "combined": {"total_cached_albums": lidarr_total + plex_total},
            }

    def get_library_sync_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get library sync history."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM library_syncs 
                ORDER BY started_at DESC 
                LIMIT ?
            """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    def cleanup_old_library_cache(self, days_old: int = 7) -> Dict[str, int]:
        """Clean up library cache entries that haven't been updated recently."""
        cutoff_date = datetime.now() - timedelta(days=days_old)

        with self._get_connection() as conn:
            # Count what will be removed
            lidarr_count = conn.execute(
                """
                SELECT COUNT(*) as count FROM lidarr_albums WHERE last_updated < ?
            """,
                (cutoff_date,),
            ).fetchone()["count"]

            plex_count = conn.execute(
                """
                SELECT COUNT(*) as count FROM plex_albums WHERE last_updated < ?
            """,
                (cutoff_date,),
            ).fetchone()["count"]

            # Remove old entries
            conn.execute(
                "DELETE FROM lidarr_albums WHERE last_updated < ?", (cutoff_date,)
            )
            conn.execute(
                "DELETE FROM plex_albums WHERE last_updated < ?", (cutoff_date,)
            )

            conn.commit()

        return {
            "lidarr_removed": lidarr_count,
            "plex_removed": plex_count,
            "total_removed": lidarr_count + plex_count,
        }

    def _row_to_album_dict(self, row) -> Dict[str, Any]:
        """Convert database row to album dictionary."""
        return {
            "id": row["id"],
            "title": row["title"],
            "artist": row["artist"],
            "year": row["year"],
            "mbid": row["mbid"],
            "type": row["type"],
            "source": row["source"],
            "cover_art_url": row["cover_art_url"],
            "external_ratings": json.loads(row["external_ratings"] or "{}"),
            "tags": json.loads(row["tags"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_recommendation_dict(self, row) -> Dict[str, Any]:
        """Convert database row to recommendation dictionary."""
        return {
            "id": row["id"],
            "title": row["title"],
            "artist": row["artist"],
            "year": row["year"],
            "mbid": row["mbid"],
            "status": row["status"],
            "discovered_date": row["discovered_date"],
            "similarity_score": row["similarity_score"],
            "cover_art_url": row["cover_art_url"],
            "external_ratings": json.loads(row["external_ratings"] or "{}"),
            "tags": json.loads(row["tags"] or "[]"),
            "user_notes": row["user_notes"] or "",
            "error_message": row["error_message"] or "",
        }
