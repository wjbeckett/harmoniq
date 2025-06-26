"""
Lidarr API client for Harmoniq Library Grower feature.
Handles communication with Lidarr for album management.
"""

import logging
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


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
