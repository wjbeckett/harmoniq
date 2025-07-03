"""
Modified Library Grower for Album Discovery - SQLite Version
Enhanced discovery engine with SQLite integration and all original functionality
"""

import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import requests
import urllib.parse
from typing import Optional

from harmoniq import config

from .recommendation_manager import (
    AlbumRecommendationManager,
    StatsTracker,
    RecommendationStatus,
)
from .lastfm_client import LastfmClient
from .musicbrainz_client import MusicBrainzClient
from .lidarr_client import LidarrClient

logger = logging.getLogger(__name__)


def get_robust_cover_art_url(mbid: str, artist: str, album: str) -> str:
    """
    Get cover art URL from multiple external sources with guaranteed fallback.
    """

    # Try external sources in order of preference
    external_url = try_external_cover_sources(mbid, artist, album)
    if external_url:
        return external_url

    # Final fallback: High-quality placeholder with album info
    return generate_placeholder_cover_url(artist, album)


def try_external_cover_sources(mbid: str, artist: str, album: str) -> Optional[str]:
    """Try multiple external cover art sources."""

    # Source 1: Multiple Cover Art Archive URLs
    cover_archive_urls = [
        f"https://coverartarchive.org/release/{mbid}/front-250",
        f"https://coverartarchive.org/release/{mbid}/front-500",
        f"https://coverartarchive.org/release/{mbid}/front",
        f"https://coverartarchive.org/release-group/{mbid}/front-250",
    ]

    for url in cover_archive_urls:
        if test_url_works(url):
            logger.info(f"Found Cover Art Archive: {url}")
            return url

    # Source 2: Spotify Web API (no auth required for search)
    spotify_url = get_spotify_cover(artist, album)
    if spotify_url and test_url_works(spotify_url):
        logger.info(f"Found Spotify cover: {spotify_url}")
        return spotify_url

    # Source 3: Last.fm API (if available)
    if hasattr(config, "LASTFM_API_KEY") and config.LASTFM_API_KEY:
        lastfm_url = get_lastfm_cover(artist, album)
        if lastfm_url and test_url_works(lastfm_url):
            logger.info(f"Found Last.fm cover: {lastfm_url}")
            return lastfm_url

    logger.warning(f"No external cover found for {artist} - {album}")
    return None


def test_url_works(url: str, timeout: int = 5) -> bool:
    """Test if a URL returns a valid image."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"URL test failed for {url}: {e}")
        return False


def get_spotify_cover(artist: str, album: str) -> Optional[str]:
    """Get cover from Spotify Web API (no authentication required for search)."""
    try:
        # Clean up artist and album names for better search
        artist_clean = artist.replace("&", "and").strip()
        album_clean = album.replace("&", "and").strip()

        search_query = f'artist:"{artist_clean}" album:"{album_clean}"'
        search_url = f"https://api.spotify.com/v1/search?q={urllib.parse.quote(search_query)}&type=album&limit=5"

        headers = {"User-Agent": "Harmoniq/1.0"}

        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            albums = data.get("albums", {}).get("items", [])

            for album_item in albums:
                images = album_item.get("images", [])
                if images:
                    # Prefer medium size images (usually 300x300)
                    for img in images:
                        if img.get("height", 0) >= 250:
                            return img["url"]
                    # Fallback to any image
                    return images[0]["url"]

        return None
    except Exception as e:
        logger.debug(f"Spotify cover lookup failed for {artist} - {album}: {e}")
        return None


def get_lastfm_cover(artist: str, album: str) -> Optional[str]:
    """Get cover from Last.fm API."""
    try:
        import pylast

        network = pylast.LastFMNetwork(api_key=config.LASTFM_API_KEY)
        album_obj = network.get_album(artist, album)
        cover_url = album_obj.get_cover_image(size=pylast.COVER_LARGE)
        return cover_url if cover_url else None
    except Exception as e:
        logger.debug(f"Last.fm cover lookup failed for {artist} - {album}: {e}")
        return None


def generate_placeholder_cover_url(artist: str, album: str) -> str:
    """Generate a high-quality placeholder cover URL with album info."""
    # Clean and truncate text for URL
    artist_short = artist[:25] + "..." if len(artist) > 25 else artist
    album_short = album[:25] + "..." if len(album) > 25 else album

    # Create readable text
    text = f"{artist_short}|{album_short}".replace(" ", "+").replace("&", "and")

    # Use a high-quality placeholder service with music theme
    return f"https://via.placeholder.com/300x300/2c3e50/ecf0f1?text={urllib.parse.quote(text)}"


class AlbumDiscoveryEngine:
    """Discovers new albums and stores them as recommendations using SQLite."""

    def __init__(self, config, stats_tracker=None, sync_manager=None):
        self.config = config

        # Store sync manager reference
        self.sync_manager = sync_manager

        logger.info(
            f"🔧 Discovery engine initialized with sync_manager: {sync_manager is not None}"
        )
        if sync_manager:
            logger.info(f"🔧 Sync manager type: {type(sync_manager)}")
            logger.info(
                f"🔧 Sync manager cache built: {getattr(sync_manager, '_cache_built', 'unknown')}"
            )
        else:
            logger.info("🔧 No sync manager provided to discovery engine!")

        # Initialize SQLite-based systems
        config_dir = os.path.dirname(config.CONFIG_FILE_PATH)
        self.recommendation_manager = AlbumRecommendationManager(config_dir)

        # Use provided stats tracker or create new one
        if stats_tracker:
            self.stats_tracker = stats_tracker
        else:
            self.stats_tracker = StatsTracker(config_dir)

        # Initialize clients
        self.lastfm_client = LastfmClient(
            api_key=config.LASTFM_API_KEY, api_user=config.LASTFM_USER
        )
        self.musicbrainz_client = MusicBrainzClient()
        self.lidarr_client = LidarrClient(
            base_url=config.LIDARR_URL, api_key=config.LIDARR_API_KEY
        )

    async def run_discovery_cycle(self) -> Dict[str, Any]:
        """Run a complete album discovery cycle with SQLite tracking."""
        logger.info("Starting album discovery cycle...")

        # Start discovery run tracking in database
        run_id = self.recommendation_manager.db.start_discovery_run()

        discovery_results = {
            "started_at": datetime.now().isoformat(),
            "albums_discovered": 0,
            "new_recommendations": 0,
            "errors": [],
            "artists_processed": 0,
            "similar_artists_found": 0,
            "albums_filtered": 0,
            "run_id": run_id,
        }

        try:
            # Update stats
            self.stats_tracker.record_activity(
                "Starting album discovery cycle", "discovery"
            )

            # Get user's top artists from Last.fm
            logger.info("Fetching top artists from Last.fm...")
            top_artists = await self._get_top_artists()

            if not top_artists:
                logger.warning("No top artists found from Last.fm")
                discovery_results["errors"].append("No top artists found from Last.fm")
                return discovery_results

            logger.info(f"Found {len(top_artists)} top artists")
            discovery_results["artists_processed"] = len(top_artists)

            # Find similar artists for each top artist
            all_similar_artists = set()
            for artist in top_artists:
                try:
                    similar = await self._get_similar_artists(artist["name"])
                    all_similar_artists.update(similar)
                    logger.debug(
                        f"Found {len(similar)} similar artists for {artist['name']}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error finding similar artists for {artist['name']}: {e}"
                    )
                    discovery_results["errors"].append(
                        f"Similar artists error for {artist['name']}: {str(e)}"
                    )

            discovery_results["similar_artists_found"] = len(all_similar_artists)
            logger.info(f"Found {len(all_similar_artists)} unique similar artists")

            # Get albums for similar artists
            discovered_albums = []
            for artist_name in all_similar_artists:
                try:
                    albums = await self._get_artist_albums(artist_name)
                    discovered_albums.extend(albums)
                    logger.debug(f"Found {len(albums)} albums for {artist_name}")
                except Exception as e:
                    logger.error(f"Error getting albums for {artist_name}: {e}")
                    discovery_results["errors"].append(
                        f"Albums error for {artist_name}: {str(e)}"
                    )

            discovery_results["albums_discovered"] = len(discovered_albums)
            logger.info(f"Discovered {len(discovered_albums)} total albums")

            # Filter albums (remove duplicates, already owned, etc.)
            filtered_albums = await self._filter_albums(discovered_albums)
            discovery_results["albums_filtered"] = len(discovered_albums) - len(
                filtered_albums
            )

            logger.info(f"After filtering: {len(filtered_albums)} new albums")

            # Store as recommendations
            new_recommendations = 0
            for album in filtered_albums:
                try:
                    # Enhance album data with additional metadata
                    enhanced_album = await self._enhance_album_metadata(album)

                    # Add to recommendations using SQLite system
                    album_id = self.recommendation_manager.add_recommendation(
                        enhanced_album
                    )
                    if album_id:
                        new_recommendations += 1
                        logger.debug(
                            f"Added recommendation: {album['artist']} - {album['title']}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error adding recommendation for {album.get('artist')} - {album.get('title')}: {e}"
                    )
                    discovery_results["errors"].append(
                        f"Recommendation error: {str(e)}"
                    )

            discovery_results["new_recommendations"] = new_recommendations

            # Update stats
            self.stats_tracker.record_activity(
                f"Discovery complete: {new_recommendations} new recommendations",
                "discovery",
            )

            logger.info(
                f"Discovery cycle complete: {new_recommendations} new recommendations"
            )

        except Exception as e:
            logger.error(f"Discovery cycle failed: {e}")
            discovery_results["errors"].append(f"Discovery cycle error: {str(e)}")

            self.stats_tracker.record_activity(
                f"Discovery cycle failed: {str(e)}", "error"
            )

        finally:
            # Update discovery run in database
            discovery_results["completed_at"] = datetime.now().isoformat()
            self.recommendation_manager.db.update_discovery_run(
                run_id, discovery_results
            )

        return discovery_results

    async def _get_top_artists(self) -> List[Dict[str, Any]]:
        """Get user's top artists from Last.fm."""
        try:
            # Get different time periods for variety
            periods = ["overall", "12month", "6month"]
            all_artists = []

            for period in periods:
                # Use the correct config keys
                artists = self.lastfm_client.get_user_top_artists(
                    period=period,
                    limit=self.config.LIBRARY_GROWER_TOP_ARTISTS_COUNT,
                )
                all_artists.extend(artists)

            # Remove duplicates while preserving order
            seen = set()
            unique_artists = []
            for artist in all_artists:
                if artist["name"] not in seen:
                    seen.add(artist["name"])
                    unique_artists.append(artist)

            # Use the top artists count as max limit too
            return unique_artists[: self.config.LIBRARY_GROWER_TOP_ARTISTS_COUNT]

        except Exception as e:
            logger.error(f"Error getting top artists: {e}")
            return []

    async def _get_similar_artists(self, artist_name: str) -> List[str]:
        """Get similar artists from Last.fm."""
        try:
            similar_artists = self.lastfm_client.get_similar_artists(
                artist_name=artist_name,
                limit=self.config.LIBRARY_GROWER_SIMILAR_ARTISTS_PER_TOP_ARTIST,
            )
            return [artist["name"] for artist in similar_artists]
        except Exception as e:
            logger.error(f"Error getting similar artists for {artist_name}: {e}")
            return []

    async def _get_artist_albums(self, artist_name: str) -> List[Dict[str, Any]]:
        """Get studio albums for an artist."""
        try:
            # First get albums from Last.fm
            lastfm_albums = self.lastfm_client.get_artist_top_albums(
                artist_name=artist_name,
                limit=self.config.LIBRARY_GROWER_ALBUMS_PER_SIMILAR_ARTIST,
            )

            studio_albums = []
            processed_album_names = set()  # Avoid duplicates

            for album in lastfm_albums:
                album_name = album["name"]

                # Skip if we've already processed this album name
                if album_name.lower() in processed_album_names:
                    continue
                processed_album_names.add(album_name.lower())

                album_mbid = album.get("mbid")
                best_match = None

                # Strategy 1: If Last.fm provided an MBID, check it first
                if album_mbid:
                    best_match = await self._check_album_mbid(
                        album_mbid, album_name, artist_name
                    )

                # Strategy 2: If no good match yet, search MusicBrainz by name
                if not best_match:
                    search_results = self.musicbrainz_client.search_releases_by_name(
                        album_name, artist_name
                    )
                    if search_results:
                        # Take the first result (highest priority = Album over Single)
                        best_result = search_results[0]
                        best_match = {
                            "title": album_name,
                            "artist": artist_name,
                            "year": None,
                            "mbid": best_result["mbid"],
                            "type": "studio",
                            "source": "lastfm_musicbrainz_search",
                            "primary_type": best_result["primary_type"],
                        }
                        logger.debug(
                            f"Found {best_result['primary_type']} via search: '{album_name}' by {artist_name}"
                        )

                if best_match:
                    studio_albums.append(best_match)

            logger.info(f"Found {len(studio_albums)} studio albums for {artist_name}")
            return studio_albums

        except Exception as e:
            logger.error(f"Error getting albums for {artist_name}: {e}")
            return []

    async def _check_album_mbid(
        self, album_mbid: str, album_name: str, artist_name: str
    ) -> Optional[Dict[str, Any]]:
        """Check a specific MBID and return album info if it's a studio album."""
        # First try to get release group MBID from the album MBID
        release_group_mbid = (
            self.musicbrainz_client.get_release_group_mbid_from_album_mbid(album_mbid)
        )

        if release_group_mbid:
            type_info = self.musicbrainz_client.get_album_type_by_release_group_mbid(
                release_group_mbid
            )
            if type_info and type_info.get("is_studio_album", False):
                return {
                    "title": album_name,
                    "artist": artist_name,
                    "year": None,
                    "mbid": release_group_mbid,
                    "type": "studio",
                    "source": "lastfm_musicbrainz_discovery",
                    "primary_type": type_info.get("primary_type", "Unknown"),
                }

        # Try the original MBID directly
        type_info = self.musicbrainz_client.get_album_type_by_release_group_mbid(
            album_mbid
        )
        if type_info and type_info.get("is_studio_album", False):
            return {
                "title": album_name,
                "artist": artist_name,
                "year": None,
                "mbid": album_mbid,
                "type": "studio",
                "source": "lastfm_musicbrainz_discovery",
                "primary_type": type_info.get("primary_type", "Unknown"),
            }

        return None

    async def _filter_albums(
        self, albums: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter out albums that shouldn't be recommended using fast cache lookups."""
        filtered = []

        # First, ensure the sync manager is actually available and ready.
        if not hasattr(self, "sync_manager") or not self.sync_manager._initialized:
            logger.error(
                "CRITICAL: Sync Manager not available or not initialized. "
                "Cannot filter against library. Aborting discovery run to "
                "prevent duplicate recommendations."
            )
            return []

        logger.info(
            f"Filtering {len(albums)} discovered albums against the library cache..."
        )

        # Get existing recommendations from SQLite to avoid duplicates in this run.
        existing_recommendations = (
            self.recommendation_manager.get_recommendations_by_status()
        )
        existing_rec_titles = {
            f"{rec['artist']}_{rec['title']}".lower()
            for rec in existing_recommendations
        }

        for album in albums:
            artist_name = album.get("artist")
            album_title = album.get("title")

            # Skip if the album data is malformed
            if not artist_name or not album_title:
                continue

            # Check 1: Is it already in our recommendations database?
            album_key = f"{artist_name}_{album_title}".lower()
            if album_key in existing_rec_titles:
                logger.debug(f"Skipping '{album_key}', already in recommendations DB.")
                continue

            album_status = self.sync_manager.album_exists_by_name(
                artist_name, album_title
            )

            if album_status["in_any_library"]:
                logger.info(
                    f"✅ Skipping '{artist_name} - {album_title}', it is already in the library (Plex or Lidarr)."
                )
                continue

            # Check 2: Skip if album year is invalid (no change here)
            max_year = datetime.now().year + 1
            if album.get("year") and album["year"] > max_year:
                continue

            # If all checks have passed, this is a genuinely new recommendation.
            filtered.append(album)

        return filtered

    async def _enhance_album_metadata(self, album: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance album with additional metadata for better recommendations."""
        enhanced = album.copy()

        try:
            # Add cover art URL with robust fallback system
            if album.get("mbid"):
                enhanced["cover_art_url"] = get_robust_cover_art_url(
                    album["mbid"],
                    album.get("artist", "Unknown Artist"),
                    album.get("title", "Unknown Album"),
                )

            # Add Last.fm data if available
            try:
                lastfm_album = await self.lastfm_client.get_album_info(
                    album["artist"], album["title"]
                )
                if lastfm_album:
                    enhanced["external_ratings"] = {
                        "lastfm_listeners": lastfm_album.get("listeners"),
                        "lastfm_playcount": lastfm_album.get("playcount"),
                        "lastfm_tags": lastfm_album.get("tags", []),
                    }
                    enhanced["tags"] = lastfm_album.get("tags", [])
            except Exception as e:
                logger.debug(
                    f"Could not get Last.fm data for {album['artist']} - {album['title']}: {e}"
                )

            # Calculate similarity score (placeholder - could be enhanced)
            enhanced["similarity_score"] = 0.8  # Default high similarity

        except Exception as e:
            logger.error(f"Error enhancing album metadata: {e}")

        return enhanced

    async def process_approved_recommendations(self) -> Dict[str, Any]:
        """Process approved recommendations by adding them to Lidarr."""
        logger.info("Processing approved recommendations...")

        results = {
            "started_at": datetime.now().isoformat(),
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "errors": [],
        }

        try:
            # Get approved recommendations from SQLite
            approved = self.recommendation_manager.get_approved_recommendations()

            if not approved:
                logger.info("No approved recommendations to process")
                return results

            logger.info(f"Processing {len(approved)} approved recommendations")

            for recommendation in approved:
                try:
                    # Update status to processing
                    self.recommendation_manager.update_recommendation_status(
                        recommendation["id"], RecommendationStatus.PROCESSING
                    )

                    # Add to Lidarr
                    success = await self._add_album_to_lidarr(recommendation)

                    if success:
                        # Update status to added
                        self.recommendation_manager.update_recommendation_status(
                            recommendation["id"], RecommendationStatus.ADDED
                        )

                        # Add to recently added (for the ribbon) using SQLite
                        self.stats_tracker.record_album_added(recommendation)

                        results["successful"] += 1
                        logger.info(
                            f"Successfully added: {recommendation['artist']} - {recommendation['title']}"
                        )

                    else:
                        # Update status to failed
                        self.recommendation_manager.update_recommendation_status(
                            recommendation["id"],
                            RecommendationStatus.FAILED,
                            error_message="Failed to add to Lidarr",
                        )
                        results["failed"] += 1
                        results["errors"].append(
                            f"Failed to add: {recommendation['artist']} - {recommendation['title']}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error processing recommendation {recommendation['id']}: {e}"
                    )
                    self.recommendation_manager.update_recommendation_status(
                        recommendation["id"],
                        RecommendationStatus.FAILED,
                        error_message=str(e),
                    )
                    results["failed"] += 1
                    results["errors"].append(f"Processing error: {str(e)}")

                results["processed"] += 1

            logger.info(
                f"Processing complete: {results['successful']} successful, {results['failed']} failed"
            )

        except Exception as e:
            logger.error(f"Error processing approved recommendations: {e}")
            results["errors"].append(f"Processing error: {str(e)}")

        results["completed_at"] = datetime.now().isoformat()
        return results

    async def _add_album_to_lidarr(self, recommendation: Dict[str, Any]) -> bool:
        """Add an approved recommendation to Lidarr."""
        try:
            # Use existing Lidarr client method
            success = await self.lidarr_client.add_album(
                artist_name=recommendation["artist"],
                album_title=recommendation["title"],
                musicbrainz_id=recommendation.get("mbid"),
            )
            return success
        except Exception as e:
            logger.error(f"Error adding album to Lidarr: {e}")
            return False
