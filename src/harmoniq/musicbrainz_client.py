"""
MusicBrainz API client for Harmoniq Library Grower feature.
Handles fetching album type information for accurate filtering.
"""

import logging
import musicbrainzngs
from typing import Optional, Dict, List, Set
from time import sleep

logger = logging.getLogger(__name__)


class MusicBrainzClient:
    """Client for interacting with MusicBrainz API."""

    # Define album types we want to include (studio albums)
    DESIRED_PRIMARY_TYPES = {"Album"}
    DESIRED_SECONDARY_TYPES = {"Studio"}

    # Define album types we want to exclude
    EXCLUDED_PRIMARY_TYPES = {"Single", "EP", "Broadcast", "Other"}
    EXCLUDED_SECONDARY_TYPES = {
        "Live",
        "Compilation",
        "Soundtrack",
        "Spokenword",
        "Interview",
        "Audiobook",
        "Mixtape/Street",
        "Demo",
    }

    def __init__(
        self,
        app_name: str = "Harmoniq",
        app_version: str = "1.0",
        contact_email: Optional[str] = None,
        rate_limit_delay: float = 1.0,
    ):
        """
        Initialize MusicBrainz client.

        Args:
            app_name: Application name for MusicBrainz API
            app_version: Application version
            contact_email: Contact email (recommended by MusicBrainz)
            rate_limit_delay: Delay between requests to respect rate limits
        """
        self.rate_limit_delay = rate_limit_delay

        # Set user agent for MusicBrainz API
        musicbrainzngs.set_useragent(app_name, app_version, contact_email)

        # Set rate limiting to be respectful
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

        logger.info(f"Initialized MusicBrainz client: {app_name} v{app_version}")

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        if self.rate_limit_delay > 0:
            sleep(self.rate_limit_delay)

    def get_album_type_by_release_group_mbid(
        self, release_group_mbid: str
    ) -> Optional[Dict[str, any]]:
        """
        Get album type information by MusicBrainz Release Group ID.

        Args:
            release_group_mbid: MusicBrainz Release Group ID

        Returns:
            Dictionary with type information:
            {
                'primary_type': str,
                'secondary_types': List[str],
                'is_studio_album': bool,
                'title': str,
                'artist': str
            }
            Returns None if not found or error occurs.
        """
        try:
            self._rate_limit()

            logger.debug(f"Fetching release group info for MBID: {release_group_mbid}")

            # Fetch release group with artist credits
            result = musicbrainzngs.get_release_group_by_id(
                release_group_mbid, includes=["artist-credits"]
            )

            if not result or "release-group" not in result:
                logger.warning(f"No release group found for MBID: {release_group_mbid}")
                return None

            release_group = result["release-group"]

            # Extract type information
            primary_type = release_group.get("primary-type", "")
            secondary_types = release_group.get("secondary-type-list", [])

            # Extract basic info
            title = release_group.get("title", "")
            artist_name = ""
            if "artist-credit" in release_group and release_group["artist-credit"]:
                artist_name = (
                    release_group["artist-credit"][0].get("artist", {}).get("name", "")
                )

            # Determine if this is a studio album we want
            is_studio_album = self._is_desired_studio_album(
                primary_type, secondary_types
            )

            type_info = {
                "primary_type": primary_type,
                "secondary_types": secondary_types,
                "is_studio_album": is_studio_album,
                "title": title,
                "artist": artist_name,
            }

            logger.debug(
                f"Album type info for '{title}' by '{artist_name}': "
                f"primary={primary_type}, secondary={secondary_types}, "
                f"is_studio_album={is_studio_album}"
            )

            return type_info

        except musicbrainzngs.NetworkError as e:
            logger.error(
                f"Network error fetching MusicBrainz data for {release_group_mbid}: {e}"
            )
            return None
        except musicbrainzngs.ResponseError as e:
            logger.error(f"MusicBrainz API error for {release_group_mbid}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error fetching MusicBrainz data for {release_group_mbid}: {e}"
            )
            return None

    def _is_desired_studio_album(
        self, primary_type: str, secondary_types: List[str]
    ) -> bool:
        """
        Determine if an album matches our criteria for a studio album.

        Args:
            primary_type: Primary release type
            secondary_types: List of secondary release types

        Returns:
            True if this is a desired studio album, False otherwise
        """
        # Convert to sets for easier comparison
        secondary_set = set(secondary_types) if secondary_types else set()

        # Check if primary type is excluded
        if primary_type in self.EXCLUDED_PRIMARY_TYPES:
            return False

        # Check if any secondary type is excluded
        if secondary_set.intersection(self.EXCLUDED_SECONDARY_TYPES):
            return False

        # For albums, prefer those explicitly marked as Studio
        if primary_type == "Album":
            # If no secondary types specified, assume it's a studio album
            if not secondary_set:
                return True
            # If Studio is explicitly listed, it's good
            if "Studio" in secondary_set:
                return True
            # If it has other secondary types but not excluded ones, it's probably okay
            return True

        return False

    def get_release_group_mbid_from_album_mbid(self, album_mbid: str) -> Optional[str]:
        """
        Get Release Group MBID from an Album (Release) MBID.
        Sometimes Last.fm provides Release MBIDs instead of Release Group MBIDs.

        Args:
            album_mbid: MusicBrainz Release (Album) ID

        Returns:
            Release Group MBID if found, None otherwise
        """
        try:
            self._rate_limit()

            logger.debug(
                f"Fetching release info to get release group MBID for: {album_mbid}"
            )

            result = musicbrainzngs.get_release_by_id(
                album_mbid, includes=["release-groups"]
            )

            if not result or "release" not in result:
                logger.warning(f"No release found for MBID: {album_mbid}")
                return None

            release = result["release"]
            release_group = release.get("release-group", {})
            release_group_mbid = release_group.get("id")

            if release_group_mbid:
                logger.debug(
                    f"Found release group MBID {release_group_mbid} for release {album_mbid}"
                )
                return release_group_mbid
            else:
                logger.warning(f"No release group found for release {album_mbid}")
                return None

        except musicbrainzngs.NetworkError as e:
            logger.error(f"Network error fetching release data for {album_mbid}: {e}")
            return None
        except musicbrainzngs.ResponseError as e:
            logger.error(f"MusicBrainz API error for {album_mbid}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error fetching release data for {album_mbid}: {e}"
            )
            return None

    def batch_get_album_types(
        self, release_group_mbids: List[str]
    ) -> Dict[str, Optional[Dict]]:
        """
        Get album type information for multiple Release Group MBIDs.

        Args:
            release_group_mbids: List of MusicBrainz Release Group IDs

        Returns:
            Dictionary mapping MBID to type info (or None if failed)
        """
        results = {}

        logger.info(
            f"Fetching album types for {len(release_group_mbids)} release groups"
        )

        for i, mbid in enumerate(release_group_mbids):
            logger.debug(f"Processing {i+1}/{len(release_group_mbids)}: {mbid}")
            results[mbid] = self.get_album_type_by_release_group_mbid(mbid)

        successful_count = sum(1 for v in results.values() if v is not None)
        logger.info(
            f"Successfully fetched type info for {successful_count}/{len(release_group_mbids)} albums"
        )

        return results
