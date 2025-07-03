"""
Library Sync Manager for Harmoniq
Handles coordinated syncing of Plex and Lidarr libraries with smart caching.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
import threading
import time
import unicodedata
import re

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Statistics for a sync operation."""

    plex_albums: int = 0
    lidarr_albums: int = 0
    total_albums: int = 0
    sync_duration: float = 0.0
    last_sync_time: Optional[datetime] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class LibrarySyncManager:
    """
    Manages coordinated syncing of Plex and Lidarr libraries with smart caching.
    """

    def __init__(self, plex_client, lidarr_client, database):
        """
        Initialize the sync manager.

        Args:
            plex_client: PlexClient instance
            lidarr_client: LidarrClient instance
            database: HarmoniqDatabase instance
        """
        self.plex_client = plex_client
        self.lidarr_client = lidarr_client
        self.database = database

        # In-memory caches for fast lookups
        self._plex_mbids = set()
        self._lidarr_mbids = set()
        self._plex_name_cache = {}
        self._lidarr_name_cache = {}
        self._cache_built = False
        self._last_full_sync = None

        # Background sync control
        self._background_task: Optional[asyncio.Task] = None
        self._sync_lock = threading.Lock()
        self._shutdown_event = threading.Event()

        logger.info("Library Sync Manager initialized")

    def startup_sync(self) -> Dict[str, Any]:
        """
        Perform full sync on startup and build initial cache.

        Returns:
            Dictionary with sync results
        """
        logger.info("🚀 Starting up - performing full library sync...")

        with self._sync_lock:
            start_time = time.time()

            try:
                # Perform full sync of both libraries
                sync_result = self._perform_full_sync()

                if sync_result["success"]:
                    # Build in-memory cache
                    self._build_cache()
                    self._last_full_sync = datetime.now()

                    duration = time.time() - start_time
                    logger.info(f"✅ Startup sync completed in {duration:.1f}s")

                    return {
                        "success": True,
                        "sync_type": "startup_full",
                        "duration": duration,
                        "plex_mbids": len(self._plex_mbids),
                        "plex_name_cache": len(self._plex_name_cache),
                        "lidarr_mbids": len(self._lidarr_mbids),
                        "lidarr_name_cache": len(self._lidarr_name_cache),
                        "total_unique_mbids": len(
                            self._plex_mbids | self._lidarr_mbids
                        ),
                        "total_name_cache": len(self._plex_name_cache)
                        + len(self._lidarr_name_cache),
                        "cache_built": self._cache_built,
                    }
                else:
                    logger.error("❌ Startup sync failed")
                    return sync_result

            except Exception as e:
                logger.error(f"❌ Startup sync error: {e}")
                return {"success": False, "error": str(e)}

    def pre_discovery_check(self) -> Dict[str, Any]:
        """
        Quick check before discovery runs - uses cache + incremental sync if needed.

        Returns:
            Dictionary with check results
        """
        logger.info("🔍 Pre-discovery library check...")

        try:
            # If cache not built, do quick sync
            if not self._cache_built:
                logger.info("Cache not built - performing quick sync")
                return self._quick_sync()

            # Check if we need incremental sync (if last sync was > 1 hour ago)
            if self._should_do_incremental_sync():
                logger.info("Performing incremental sync")
                return self._incremental_sync()
            else:
                logger.info("Cache is fresh - using cached data")
                return {
                    "success": True,
                    "sync_type": "cache_hit",
                    "plex_albums": len(self._plex_mbids),
                    "lidarr_albums": len(self._lidarr_mbids),
                    "cache_age_minutes": self._get_cache_age_minutes(),
                }

        except Exception as e:
            logger.error(f"Pre-discovery check error: {e}")
            return {"success": False, "error": str(e)}

    @property
    def plex_cache(self):
        """Get Plex cache for external access."""
        return self._plex_mbids

    @property
    def lidarr_cache(self):
        """Get Lidarr cache for external access."""
        return self._lidarr_mbids

    def is_album_in_library(self, mbid: str) -> Dict[str, bool]:
        """
        Fast check if album exists in either library using cache.

        Args:
            mbid: MusicBrainz Release Group ID

        Returns:
            Dictionary with existence status for each library
        """
        if not self._cache_built:
            logger.warning("Cache not built - performing database lookup")
            return self._database_album_check(mbid)

        return {
            "in_plex": mbid in self._plex_mbids,
            "in_lidarr": mbid in self._lidarr_mbids,
            "in_any_library": mbid in self._plex_mbids or mbid in self._lidarr_mbids,
        }

    def _normalize_string(self, text: str) -> str:
        """Normalize string for comparison - handle Unicode and special characters."""
        if not text:
            return ""

        # First, normalize Unicode characters to decomposed form, then recompose
        normalized = unicodedata.normalize("NFKC", text)

        # Convert to lowercase and strip whitespace
        normalized = normalized.lower().strip()

        # Replace ALL types of quotes and apostrophes with standard ASCII
        quote_chars = [
            """, """,
            '"',
            '"',
            "`",
            "´",
            "′",
            "″",
            "'",
            "'",  # These are the key ones!
        ]
        for quote_char in quote_chars:
            normalized = normalized.replace(quote_char, "'")

        # Debug for Angels & Airwaves
        if "whisper" in normalized:
            logger.debug(f"🔧 AFTER HEX: {normalized.encode('utf-8').hex()}")

        # Replace ALL types of dashes and hyphens with standard ASCII
        dash_chars = ["–", "—", "‐", "−", "⁻"]
        for dash_char in dash_chars:
            normalized = normalized.replace(dash_char, "-")

        # Replace other common Unicode characters
        replacements = {
            "＋": "+",  # Full-width plus
            "＆": "&",  # Full-width ampersand
            "&amp;": "&",  # HTML entity
            " and ": " & ",  # Normalize "and" to "&"
            " And ": " & ",
            " AND ": " & ",
        }

        for unicode_char, ascii_char in replacements.items():
            normalized = normalized.replace(unicode_char, ascii_char)

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def album_exists_by_name(self, artist: str, title: str) -> Dict[str, bool]:
        """Check if album exists by artist + title matching using cache."""
        try:
            # Normalize for comparison
            search_artist = self._normalize_string(artist)
            search_title = self._normalize_string(title)
            cache_key = f"{search_artist}|||{search_title}"

            # Use cache instead of database queries
            in_plex = cache_key in self._plex_name_cache
            in_lidarr = cache_key in self._lidarr_name_cache

            # DEBUG: Log for Angels & Airwaves specifically
            if "angels" in search_artist.lower():
                logger.info(f"🔍 SEARCHING FOR: '{search_artist}' - '{search_title}'")
                logger.info(f"🔍 CACHE KEY: '{cache_key}'")
                logger.info(f"🔍 FOUND: Plex={in_plex}, Lidarr={in_lidarr}")

                if not in_plex:
                    # Show some cache keys for debugging
                    matching_keys = [
                        k for k in self._plex_name_cache.keys() if "angels" in k
                    ]
                    logger.info(f"🔍 Angels cache keys: {matching_keys[:3]}")

            return {
                "in_plex": in_plex,
                "in_lidarr": in_lidarr,
                "in_any_library": in_plex or in_lidarr,
            }

        except Exception as e:
            logger.error(f"Error checking album by name: {e}")
            return {"in_plex": False, "in_lidarr": False, "in_any_library": False}

    def start_background_sync(self, interval_hours: int = 6):
        """
        Start background sync task that runs every N hours.

        Args:
            interval_hours: Hours between background syncs
        """
        if self._background_task and not self._background_task.done():
            logger.info("Background sync already running")
            return

        logger.info(f"Starting background sync (every {interval_hours} hours)")

        async def background_sync_loop():
            while not self._shutdown_event.is_set():
                try:
                    # Wait for interval or shutdown
                    await asyncio.sleep(interval_hours * 3600)

                    if not self._shutdown_event.is_set():
                        logger.info("🔄 Running scheduled background sync")
                        result = self._perform_full_sync()

                        if result["success"]:
                            self._build_cache()
                            self._last_full_sync = datetime.now()
                            logger.info("✅ Background sync completed")
                        else:
                            logger.error("❌ Background sync failed")

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Background sync error: {e}")

        self._background_task = asyncio.create_task(background_sync_loop())

    def stop_background_sync(self):
        """Stop the background sync task."""
        logger.info("Stopping background sync")
        self._shutdown_event.set()

        if self._background_task and not self._background_task.done():
            self._background_task.cancel()

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status and statistics.

        Returns:
            Dictionary with sync status information
        """
        return {
            "cache_built": self._cache_built,
            "last_full_sync": (
                self._last_full_sync.isoformat() if self._last_full_sync else None
            ),
            "cache_age_minutes": self._get_cache_age_minutes(),
            "plex_albums_cached": len(self._plex_mbids),
            "lidarr_albums_cached": len(self._lidarr_mbids),
            "total_unique_albums": len(self._plex_mbids | self._lidarr_mbids),
            "background_sync_running": self._background_task
            and not self._background_task.done(),
            "needs_sync": self._should_do_incremental_sync(),
        }

    def force_full_sync(self) -> Dict[str, Any]:
        """
        Force a full sync regardless of cache state.

        Returns:
            Dictionary with sync results
        """
        logger.info("🔄 Forcing full library sync...")

        with self._sync_lock:
            try:
                result = self._perform_full_sync()

                if result["success"]:
                    self._build_cache()
                    self._last_full_sync = datetime.now()
                    logger.info("✅ Forced full sync completed")

                return result

            except Exception as e:
                logger.error(f"Forced sync error: {e}")
                return {"success": False, "error": str(e)}

    # Private methods

    def _perform_full_sync(self) -> Dict[str, Any]:
        """Perform full sync of both Plex and Lidarr."""
        start_time = time.time()
        results = {"plex": {}, "lidarr": {}}
        errors = []

        # Sync Plex
        try:
            logger.info("Syncing Plex libraries...")
            results["plex"] = self.plex_client.sync_all_libraries_to_database(
                self.database
            )
            if not results["plex"]["success"]:
                errors.append(
                    f"Plex sync failed: {results['plex'].get('error', 'Unknown error')}"
                )
        except Exception as e:
            error_msg = f"Plex sync error: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            results["plex"] = {"success": False, "error": str(e)}

        # Sync Lidarr
        try:
            logger.info("Syncing Lidarr library...")
            results["lidarr"] = self.lidarr_client.sync_library_to_database(
                self.database
            )
            if not results["lidarr"]["success"]:
                errors.append(
                    f"Lidarr sync failed: {results['lidarr'].get('error', 'Unknown error')}"
                )
        except Exception as e:
            error_msg = f"Lidarr sync error: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            results["lidarr"] = {"success": False, "error": str(e)}

        # Calculate overall success
        plex_success = results["plex"] and results["plex"]["success"]
        lidarr_success = results["lidarr"] and results["lidarr"]["success"]
        overall_success = (
            plex_success or lidarr_success
        )  # Success if at least one works

        duration = time.time() - start_time

        return {
            "success": overall_success,
            "sync_type": "full",
            "duration": duration,
            "plex_result": results["plex"],
            "lidarr_result": results["lidarr"],
            "errors": errors,
            "partial_success": plex_success != lidarr_success,
        }

    def _quick_sync(self) -> Dict[str, Any]:
        """Perform quick sync and build cache."""
        logger.info("Performing quick sync...")

        result = self._perform_full_sync()

        if result["success"]:
            self._build_cache()
            self._last_full_sync = datetime.now()

        return result

    def _incremental_sync(self) -> Dict[str, Any]:
        """
        Perform incremental sync - only check for new albums since last sync.
        For now, this is simplified to a quick full sync since libraries are small.
        """
        logger.info("Performing incremental sync...")

        # With 500 albums, incremental vs full sync complexity isn't worth it
        # Just do a quick full sync - it should be fast enough
        return self._quick_sync()

    def _build_cache(self):
        """Build in-memory cache from database."""
        try:
            logger.info("Building in-memory album cache...")
            logger.info(f"🔧 Building cache at {time.time()}")

            # Get albums from database
            plex_albums = self.database.get_plex_albums()
            lidarr_albums = self.database.get_lidarr_albums()

            # ✅ ADD DEBUG LOGGING
            logger.info(
                f"🔍 DEBUG: Retrieved {len(plex_albums)} Plex albums from database"
            )
            logger.info(
                f"🔍 DEBUG: Retrieved {len(lidarr_albums)} Lidarr albums from database"
            )

            if plex_albums:
                logger.info(f"🔍 DEBUG: First Plex album: {plex_albums[0]}")
            if lidarr_albums:
                logger.info(f"🔍 DEBUG: First Lidarr album: {lidarr_albums[0]}")

            # Build MBID caches (existing logic)
            self._plex_mbids = set()
            self._lidarr_mbids = set()

            for album in plex_albums:
                mbid = self._extract_mbid_from_plex_guid(album.get("guid", ""))
                if mbid:
                    self._plex_mbids.add(mbid)

            for album in lidarr_albums:
                mbid = album.get("album_mbid", "")
                if mbid:
                    self._lidarr_mbids.add(mbid)

            # NEW: Build name-based caches for fast artist+title lookups
            self._plex_name_cache = {}
            self._lidarr_name_cache = {}

            for album in plex_albums:
                artist_name = album.get("artist_name", "")
                album_title = album.get("album_title", "")
                if artist_name and album_title:
                    # Use same normalization as album_exists_by_name
                    normalized_artist = self._normalize_string(artist_name)
                    normalized_title = self._normalize_string(album_title)
                    cache_key = f"{normalized_artist}|||{normalized_title}"
                    self._plex_name_cache[cache_key] = album

            for album in lidarr_albums:
                artist_name = album.get("artist_name", "")
                album_title = album.get("album_title", "")
                if artist_name and album_title:
                    normalized_artist = self._normalize_string(artist_name)
                    normalized_title = self._normalize_string(album_title)
                    cache_key = f"{normalized_artist}|||{normalized_title}"
                    self._lidarr_name_cache[cache_key] = album

            self._cache_built = True

            logger.info(
                f"🔍 DEBUG: Plex name cache sample keys: {list(self._plex_name_cache.keys())[:5]}"
            )
            logger.info(f"🔍 DEBUG: Looking for Angels & Airwaves albums...")
            angels_keys = [k for k in self._plex_name_cache.keys() if "angels" in k]
            logger.info(f"🔍 DEBUG: Angels keys in Plex cache: {angels_keys}")

            logger.info(
                f"Cache built: {len(self._plex_mbids)} Plex MBIDs, {len(self._lidarr_mbids)} Lidarr MBIDs"
            )
            logger.info(
                f"Name cache built: {len(self._plex_name_cache)} Plex names, {len(self._lidarr_name_cache)} Lidarr names"
            )

        except Exception as e:
            logger.error(f"Error building cache: {e}")
            self._cache_built = False

    def _extract_mbid_from_plex_guid(self, guid: str) -> Optional[str]:
        """
        Extract MusicBrainz ID from Plex GUID.
        Plex GUIDs often contain MBIDs in various formats.
        """
        if not guid:
            return None

        # Common Plex GUID formats that contain MBIDs
        # e.g., "plex://album/5d07bcb0403c6402904a8d23"
        # e.g., "mbid://12345678-1234-1234-1234-123456789012"

        # This is a simplified extraction - you might need to adjust based on your Plex setup
        if "mbid://" in guid:
            return guid.split("mbid://")[-1]

        # Add more extraction logic as needed based on your Plex GUID format
        return None

    def _should_do_incremental_sync(self) -> bool:
        """Check if incremental sync is needed."""
        if not self._last_full_sync:
            return True

        # Do incremental sync if last sync was more than 1 hour ago
        return datetime.now() - self._last_full_sync > timedelta(hours=1)

    def _get_cache_age_minutes(self) -> Optional[float]:
        """Get cache age in minutes."""
        if not self._last_full_sync:
            return None

        return (datetime.now() - self._last_full_sync).total_seconds() / 60

    def _database_album_check(self, mbid: str) -> Dict[str, bool]:
        """Fallback database check when cache not available."""
        try:
            # Check Plex albums
            plex_albums = self.database.get_plex_albums()
            in_plex = any(
                self._extract_mbid_from_plex_guid(album.get("guid", "")) == mbid
                for album in plex_albums
            )

            # Check Lidarr albums
            lidarr_albums = self.database.get_lidarr_albums()
            in_lidarr = any(
                album.get("foreignAlbumId") == mbid for album in lidarr_albums
            )

            return {
                "in_plex": in_plex,
                "in_lidarr": in_lidarr,
                "in_any_library": in_plex or in_lidarr,
            }

        except Exception as e:
            logger.error(f"Database album check error: {e}")
            return {"in_plex": False, "in_lidarr": False, "in_any_library": False}
