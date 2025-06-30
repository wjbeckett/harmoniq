"""
Lidarr API client for Harmoniq Library Grower feature.
Handles communication with Lidarr for album management.
"""

import logging
import requests
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime

logger = logging.getLogger(__name__)

from .database import LibrarySyncStatus


class LidarrClient:
    """Client for interacting with Lidarr API."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        """
        Initialize Lidarr client.

        Args:
            base_url: Lidarr base URL (e.g., "http://localhost:8686")
            api_key: Lidarr API key
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"X-Api-Key": self.api_key, "Content-Type": "application/json"}
        )

        logger.info(f"Initialized Lidarr client for {self.base_url}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Make a request to the Lidarr API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without /api/v1/ prefix)
            params: Query parameters
            json_data: JSON data for POST/PUT requests

        Returns:
            Response JSON data or None if request failed
        """
        url = urljoin(f"{self.base_url}/", f"api/v1/{endpoint.lstrip('/')}")

        try:
            logger.debug(f"Making {method} request to {url}")
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 201:
                # Created - return the created object
                return response.json()
            elif response.status_code == 404:
                logger.debug(f"Resource not found: {url}")
                return None
            else:
                logger.error(
                    f"Lidarr API request failed: {response.status_code} - {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to Lidarr failed: {e}")
            return None

    def test_connection(self) -> bool:
        """
        Test connection to Lidarr API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            result = self._make_request("GET", "system/status")
            if result:
                logger.info(
                    f"Successfully connected to Lidarr v{result.get('version', 'unknown')}"
                )
                return True
            else:
                logger.error("Failed to connect to Lidarr")
                return False
        except Exception as e:
            logger.error(f"Error testing Lidarr connection: {e}")
            return False

    def get_root_folders(self) -> List[Dict]:
        """
        Get available root folders from Lidarr.

        Returns:
            List of root folder dictionaries
        """
        result = self._make_request("GET", "rootfolder")
        return result if result else []

    def get_quality_profiles(self) -> List[Dict]:
        """
        Get available quality profiles from Lidarr.

        Returns:
            List of quality profile dictionaries
        """
        result = self._make_request("GET", "qualityprofile")
        return result if result else []

    def get_metadata_profiles(self) -> List[Dict]:
        """
        Get available metadata profiles from Lidarr.

        Returns:
            List of metadata profile dictionaries
        """
        result = self._make_request("GET", "metadataprofile")
        return result if result else []

    def search_albums_by_mbid(self, release_group_mbid: str) -> Optional[Dict]:
        """
        Search for an album by MusicBrainz Release Group ID.

        Args:
            release_group_mbid: MusicBrainz Release Group ID

        Returns:
            Album data if found, None otherwise
        """
        params = {"term": f"mbid:{release_group_mbid}"}
        result = self._make_request("GET", "search", params=params)

        if result and isinstance(result, list) and len(result) > 0:
            return result[0]  # Return first match
        return None

    def album_exists_in_library(self, release_group_mbid: str) -> bool:
        """
        Check if an album already exists in Lidarr library.

        Args:
            release_group_mbid: MusicBrainz Release Group ID

        Returns:
            True if album exists, False otherwise
        """
        # Get all albums and check for MBID match
        albums = self._make_request("GET", "album")
        if not albums:
            return False

        for album in albums:
            if album.get("foreignAlbumId") == release_group_mbid:
                logger.debug(
                    f"Album with MBID {release_group_mbid} already exists in Lidarr"
                )
                return True

        return False

    def add_album_by_mbid(
        self,
        release_group_mbid: str,
        root_folder_path: str,
        quality_profile_id: int,
        metadata_profile_id: int,
        monitored: bool = True,
        search_on_add: bool = True,
    ) -> Optional[Dict]:
        """
        Add an album to Lidarr by MusicBrainz Release Group ID.

        Args:
            release_group_mbid: MusicBrainz Release Group ID
            root_folder_path: Root folder path for the album
            quality_profile_id: Quality profile ID
            metadata_profile_id: Metadata profile ID
            monitored: Whether to monitor the album
            search_on_add: Whether to search for the album immediately

        Returns:
            Added album data if successful, None otherwise
        """
        # First, search for the album to get its details
        album_search_result = self.search_albums_by_mbid(release_group_mbid)
        if not album_search_result:
            logger.error(
                f"Could not find album with MBID {release_group_mbid} in Lidarr search"
            )
            return None

        # Check if album already exists
        if self.album_exists_in_library(release_group_mbid):
            logger.info(
                f"Album with MBID {release_group_mbid} already exists in Lidarr"
            )
            return None

        # Prepare the album data for adding
        album_data = {
            "foreignAlbumId": release_group_mbid,
            "title": album_search_result.get("title", ""),
            "artist": album_search_result.get("artist", {}),
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "metadataProfileId": metadata_profile_id,
            "monitored": monitored,
            "searchForMissingAlbums": search_on_add,
        }

        logger.info(
            f"Adding album '{album_data['title']}' by '{album_data['artist'].get('artistName', 'Unknown')}' to Lidarr"
        )

        result = self._make_request("POST", "album", json_data=album_data)

        if result:
            logger.info(
                f"Successfully added album with MBID {release_group_mbid} to Lidarr"
            )
            return result
        else:
            logger.error(
                f"Failed to add album with MBID {release_group_mbid} to Lidarr"
            )
            return None

    def get_all_albums(self) -> List[Dict]:
        """
        Get all albums from Lidarr library.

        Returns:
            List of album dictionaries
        """
        try:
            result = self._make_request("GET", "album")
            if result and isinstance(result, list):
                logger.debug(f"Retrieved {len(result)} albums from Lidarr")
                return result
            else:
                logger.warning("No albums found in Lidarr or request failed")
                return []
        except Exception as e:
            logger.error(f"Error getting albums from Lidarr: {e}")
            return []

    def get_existing_album_mbids(self) -> set:
        """
        Get set of existing album MBIDs in Lidarr library.

        Returns:
            Set of MusicBrainz Release Group IDs already in library
        """
        try:
            albums = self.get_all_albums()
            mbids = set()

            for album in albums:
                foreign_id = album.get("foreignAlbumId")
                if foreign_id:
                    mbids.add(foreign_id)

            logger.debug(f"Found {len(mbids)} existing album MBIDs in Lidarr")
            return mbids

        except Exception as e:
            logger.error(f"Error getting existing album MBIDs: {e}")
            return set()

    def get_library_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive Lidarr library statistics.

        Returns:
            Dictionary with library statistics and status info
        """
        try:
            # Get system status
            status = self._make_request("GET", "system/status")

            # Get all albums
            albums = self.get_all_albums()

            # Calculate statistics
            total_albums = len(albums)
            monitored_count = sum(
                1 for album in albums if album.get("monitored", False)
            )
            downloaded_count = sum(
                1 for album in albums if album.get("status") == "downloaded"
            )
            wanted_count = sum(
                1 for album in albums if album.get("status") in ["wanted", "missing"]
            )

            # Get quality profiles and root folders
            quality_profiles = self.get_quality_profiles()
            root_folders = self.get_root_folders()

            return {
                "success": True,
                "server_version": (
                    status.get("version", "unknown") if status else "unknown"
                ),
                "total_albums": total_albums,
                "monitored_albums": monitored_count,
                "downloaded_albums": downloaded_count,
                "wanted_albums": wanted_count,
                "quality_profiles": len(quality_profiles),
                "root_folders": len(root_folders),
                "albums_by_status": self._get_albums_by_status(albums),
            }

        except Exception as e:
            logger.error(f"Error getting Lidarr library stats: {e}")
            return {"success": False, "error": str(e)}

    def _get_albums_by_status(self, albums: List[Dict]) -> Dict[str, int]:
        """Helper method to count albums by status."""
        status_counts = {}
        for album in albums:
            status = album.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        return status_counts

    def fetch_all_library_albums(
        self, include_unmonitored: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetch all albums from Lidarr library with detailed information.

        Args:
            include_unmonitored: Whether to include unmonitored albums

        Returns:
            List of album dictionaries with standardized structure for database sync
        """
        try:
            logger.info("Fetching all albums from Lidarr library...")

            # Get all albums from Lidarr
            albums_raw = self.get_all_albums()

            if not albums_raw:
                logger.warning("No albums found in Lidarr library")
                return []

            logger.info(f"Processing {len(albums_raw)} albums from Lidarr")

            albums_processed = []
            for album in albums_raw:
                try:
                    # Skip unmonitored albums if requested
                    if not include_unmonitored and not album.get("monitored", True):
                        continue

                    # Extract album data in standardized format matching database schema
                    album_data = {
                        "id": album.get("id"),  # Lidarr internal ID
                        "title": album.get("title", ""),
                        "artist": album.get("artist", {}),  # Full artist object
                        "foreignAlbumId": album.get(
                            "foreignAlbumId", ""
                        ),  # MusicBrainz ID
                        "status": album.get("status", ""),
                        "monitored": album.get("monitored", True),
                        "qualityProfileId": album.get("qualityProfileId"),
                        "releaseDate": album.get("releaseDate", ""),
                        "path": album.get("path", ""),
                        "sizeOnDisk": album.get("sizeOnDisk", 0),
                        "dateAdded": album.get("dateAdded", ""),
                        "grabbed": album.get("grabbed", False),
                        "statistics": album.get("statistics", {}),
                        "releases": album.get("releases", []),
                        # Store full raw data for future use
                        "raw_data": album,
                    }

                    albums_processed.append(album_data)

                except Exception as e:
                    logger.warning(
                        f"Error processing Lidarr album '{album.get('title', 'unknown')}': {e}"
                    )
                    continue

            logger.info(
                f"Successfully processed {len(albums_processed)} albums from Lidarr"
            )
            return albums_processed

        except Exception as e:
            logger.error(f"Error fetching albums from Lidarr: {e}")
            return []

    def sync_library_to_database(
        self, database, include_unmonitored: bool = True
    ) -> Dict[str, Any]:
        """
        Sync Lidarr library to the database cache.

        Args:
            database: HarmoniqDatabase instance
            include_unmonitored: Whether to include unmonitored albums

        Returns:
            Dictionary with sync results and statistics
        """
        # Start library sync tracking
        sync_id = database.start_library_sync("lidarr")
        sync_start_time = datetime.now()

        try:
            logger.info("Starting Lidarr library sync to database...")

            # Test connection first
            if not self.test_connection():
                error_msg = "Cannot sync: Lidarr connection failed"
                logger.error(error_msg)
                database.complete_library_sync(
                    sync_id,
                    database.LibrarySyncStatus.FAILED,
                    {
                        "started_at": sync_start_time.isoformat(),
                        "albums_synced": 0,
                        "errors": [error_msg],
                    },
                )
                return {"success": False, "error": error_msg}

            # Fetch all albums from Lidarr
            all_albums = self.fetch_all_library_albums(
                include_unmonitored=include_unmonitored
            )

            if not all_albums:
                logger.warning("No albums found in Lidarr library")
                database.complete_library_sync(
                    sync_id,
                    LibrarySyncStatus.SUCCESS,
                    {
                        "started_at": sync_start_time.isoformat(),
                        "albums_synced": 0,
                        "albums_added": 0,
                        "albums_updated": 0,
                        "errors": [],
                    },
                )
                return {
                    "success": True,
                    "albums_synced": 0,
                    "message": "No albums found",
                }

            logger.info(f"Syncing {len(all_albums)} albums to database...")

            # Sync to database using existing method
            sync_stats = database.sync_lidarr_albums(all_albums)

            # Complete sync tracking
            database.complete_library_sync(
                sync_id,
                LibrarySyncStatus.SUCCESS,
                {
                    "started_at": sync_start_time.isoformat(),
                    "albums_synced": sync_stats["total"],
                    "albums_added": sync_stats["added"],
                    "albums_updated": sync_stats["updated"],
                    "errors": [],
                    "details": {
                        "include_unmonitored": include_unmonitored,
                        "lidarr_version": self._get_lidarr_version(),
                    },
                },
            )

            logger.info(f"Lidarr library sync completed: {sync_stats}")

            return {
                "success": True,
                "sync_id": sync_id,
                "albums_total": sync_stats["total"],
                "albums_added": sync_stats["added"],
                "albums_updated": sync_stats["updated"],
                "sync_status": "success",
            }

        except Exception as e:
            error_msg = f"Unexpected error during Lidarr library sync: {e}"
            logger.error(error_msg)

            # Complete sync with failure status
            database.complete_library_sync(
                sync_id,
                database.LibrarySyncStatus.FAILED,
                {
                    "started_at": sync_start_time.isoformat(),
                    "albums_synced": 0,
                    "errors": [error_msg],
                },
            )

            return {"success": False, "error": error_msg}

    def _get_lidarr_version(self) -> str:
        """Get Lidarr version for sync tracking."""
        try:
            status = self._make_request("GET", "system/status")
            return status.get("version", "unknown") if status else "unknown"
        except:
            return "unknown"

    def quick_library_check(self) -> Dict[str, Any]:
        """
        Quick check of Lidarr library without full sync - useful for testing connectivity.

        Returns:
            Dictionary with library information and album counts
        """
        try:
            # Test connection
            if not self.test_connection():
                return {"success": False, "error": "Lidarr connection failed"}

            # Get basic stats
            stats = self.get_library_stats()

            if not stats["success"]:
                return stats

            # Get configuration info
            quality_profiles = self.get_quality_profiles()
            root_folders = self.get_root_folders()
            metadata_profiles = self.get_metadata_profiles()

            return {
                "success": True,
                "server_version": stats["server_version"],
                "total_albums": stats["total_albums"],
                "monitored_albums": stats["monitored_albums"],
                "downloaded_albums": stats["downloaded_albums"],
                "wanted_albums": stats["wanted_albums"],
                "albums_by_status": stats["albums_by_status"],
                "configuration": {
                    "quality_profiles": len(quality_profiles),
                    "root_folders": len(root_folders),
                    "metadata_profiles": len(metadata_profiles),
                },
                "quality_profiles": [
                    {"id": qp["id"], "name": qp["name"]} for qp in quality_profiles
                ],
                "root_folders": [
                    {"id": rf["id"], "path": rf["path"]} for rf in root_folders
                ],
            }

        except Exception as e:
            logger.error(f"Error during Lidarr library check: {e}")
            return {"success": False, "error": str(e)}

    def test_library_sync(self, database, limit: int = 5) -> Dict[str, Any]:
        """
        Test library sync with a small number of albums - useful for development and testing.

        Args:
            database: HarmoniqDatabase instance
            limit: Number of albums to process for testing

        Returns:
            Dictionary with test results
        """
        try:
            logger.info(f"Testing Lidarr sync with {limit} albums...")

            # Test connection first
            if not self.test_connection():
                return {"success": False, "error": "Lidarr connection failed"}

            # Get limited albums
            all_albums = self.fetch_all_library_albums()

            if not all_albums:
                return {"success": False, "error": "No albums found in Lidarr"}

            # Limit for testing
            test_albums = all_albums[:limit]

            logger.info(f"Testing sync with {len(test_albums)} albums")

            # Test database sync
            sync_stats = database.sync_lidarr_albums(test_albums)

            return {
                "success": True,
                "albums_processed": len(test_albums),
                "albums_added": sync_stats["added"],
                "albums_updated": sync_stats["updated"],
                "sample_albums": [
                    {
                        "title": album["title"],
                        "artist": (
                            album["artist"].get("artistName", "Unknown")
                            if album["artist"]
                            else "Unknown"
                        ),
                        "status": album["status"],
                        "monitored": album["monitored"],
                    }
                    for album in test_albums[:3]  # First 3 as sample
                ],
            }

        except Exception as e:
            logger.error(f"Error during test sync: {e}")
            return {"success": False, "error": str(e)}

    def get_albums_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get albums filtered by status (downloaded, wanted, missing, etc.).

        Args:
            status: Album status to filter by

        Returns:
            List of albums with the specified status
        """
        try:
            all_albums = self.get_all_albums()
            filtered_albums = [
                album for album in all_albums if album.get("status") == status
            ]

            logger.info(f"Found {len(filtered_albums)} albums with status '{status}'")
            return filtered_albums

        except Exception as e:
            logger.error(f"Error getting albums by status '{status}': {e}")
            return []

    def get_monitored_albums(self) -> List[Dict[str, Any]]:
        """
        Get only monitored albums from Lidarr.

        Returns:
            List of monitored albums
        """
        try:
            all_albums = self.get_all_albums()
            monitored_albums = [
                album for album in all_albums if album.get("monitored", False)
            ]

            logger.info(f"Found {len(monitored_albums)} monitored albums")
            return monitored_albums

        except Exception as e:
            logger.error(f"Error getting monitored albums: {e}")
            return []
