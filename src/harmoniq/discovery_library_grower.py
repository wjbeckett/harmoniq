"""
Modified Library Grower for Album Discovery
Finds potential albums and stores them as recommendations for user approval
"""

import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from harmoniq import config

from .recommendation_storage import AlbumRecommendationManager, RecommendationStatus
from .lastfm_client import LastfmClient
from .musicbrainz_client import MusicBrainzClient
from .lidarr_client import LidarrClient

logger = logging.getLogger(__name__)


class AlbumDiscoveryEngine:
    """Discovers new albums and stores them as recommendations."""

    def __init__(self, config, stats_tracker=None):
        self.config = config
        self.stats_tracker = stats_tracker
        config_dir = os.path.dirname(config.CONFIG_FILE_PATH)
        self.recommendation_manager = AlbumRecommendationManager(config_dir)

        # Initialize clients
        self.lastfm_client = LastfmClient(
            api_key=config.LASTFM_API_KEY, api_user=config.LASTFM_USER
        )
        self.musicbrainz_client = MusicBrainzClient()
        self.lidarr_client = LidarrClient(
            base_url=config.LIDARR_URL, api_key=config.LIDARR_API_KEY
        )

    async def run_discovery_cycle(self) -> Dict[str, Any]:
        """Run a complete album discovery cycle."""
        logger.info("Starting album discovery cycle...")

        discovery_results = {
            "started_at": datetime.now().isoformat(),
            "albums_discovered": 0,
            "new_recommendations": 0,
            "errors": [],
            "artists_processed": 0,
            "similar_artists_found": 0,
            "albums_filtered": 0,
        }

        try:
            # Update stats
            if self.stats_tracker:
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

                    # Add to recommendations
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
            if self.stats_tracker:
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

            if self.stats_tracker:
                self.stats_tracker.record_activity(
                    f"Discovery cycle failed: {str(e)}", "error"
                )

        discovery_results["completed_at"] = datetime.now().isoformat()
        return discovery_results

    async def _get_top_artists(self) -> List[Dict[str, Any]]:
        """Get user's top artists from Last.fm."""
        try:
            periods = ["overall", "12month", "6month"]
            all_artists = []

            for period in periods:
                artists = self.lastfm_client.get_user_top_artists(
                    period=period,
                    limit=self.config.LIBRARY_GROWER.get("top_artists_limit", 20),
                )
                all_artists.extend(artists)

            seen = set()
            unique_artists = []
            for artist in all_artists:
                if artist["name"] not in seen:
                    seen.add(artist["name"])
                    unique_artists.append(artist)

            return unique_artists[
                : self.config.LIBRARY_GROWER.get("max_top_artists", 50)
            ]

        except Exception as e:
            logger.error(f"Error getting top artists: {e}")
            return []

    async def _get_similar_artists(self, artist_name: str) -> List[str]:
        """Get similar artists from Last.fm."""
        try:
            similar_artists = self.lastfm_client.get_similar_artists(
                artist_name=artist_name,
                limit=self.config.LIBRARY_GROWER.get("similar_artists_limit", 10),
            )
            return [artist["name"] for artist in similar_artists]
        except Exception as e:
            logger.error(f"Error getting similar artists for {artist_name}: {e}")
            return []

    async def _get_artist_albums(self, artist_name: str) -> List[Dict[str, Any]]:
        """Get studio albums for an artist."""
        try:
            lastfm_albums = self.lastfm_client.get_artist_top_albums(
                artist_name=artist_name,
                limit=self.config.LIBRARY_GROWER.get("max_albums_per_artist", 20),
            )

            studio_albums = []

            for album in lastfm_albums:
                album_mbid = album.get("mbid")
                if not album_mbid:
                    logger.debug(
                        f"No MBID for album '{album['name']}' by {artist_name}, skipping type check"
                    )
                    continue

                type_info = (
                    self.musicbrainz_client.get_album_type_by_release_group_mbid(
                        album_mbid
                    )
                )

                if type_info and type_info.get("is_studio_album", False):
                    studio_albums.append(
                        {
                            "title": album["name"],
                            "artist": artist_name,
                            "year": None,
                            "mbid": album_mbid,
                            "type": "studio",
                            "source": "lastfm_musicbrainz_discovery",
                        }
                    )

            logger.info(f"Found {len(studio_albums)} studio albums for {artist_name}")
            return studio_albums

        except Exception as e:
            logger.error(f"Error getting albums for {artist_name}: {e}")
            return []

    async def _filter_albums(
        self, albums: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter out albums that shouldn't be recommended."""
        filtered = []

        # Get existing Lidarr albums to avoid duplicates
        try:
            existing_albums = await self.lidarr_client.get_all_albums()
            existing_titles = {
                f"{album['artist']}_{album['title']}".lower()
                for album in existing_albums
            }
        except Exception as e:
            logger.warning(f"Could not fetch existing Lidarr albums: {e}")
            existing_titles = set()

        # Get existing recommendations to avoid duplicates
        existing_recommendations = (
            self.recommendation_manager.get_recommendations_by_status()
        )
        existing_rec_titles = {
            f"{rec['artist']}_{rec['title']}".lower()
            for rec in existing_recommendations
        }

        for album in albums:
            album_key = f"{album['artist']}_{album['title']}".lower()

            # Skip if already in Lidarr
            if album_key in existing_titles:
                continue

            # Skip if already recommended
            if album_key in existing_rec_titles:
                continue

            # Skip if too old (configurable)
            min_year = self.config.LIBRARY_GROWER.get("min_album_year", 1960)
            if album.get("year") and album["year"] < min_year:
                continue

            # Skip if too new (might not be available yet)
            max_year = datetime.now().year + 1
            if album.get("year") and album["year"] > max_year:
                continue

            filtered.append(album)

        return filtered

    async def _enhance_album_metadata(self, album: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance album with additional metadata for better recommendations."""
        enhanced = album.copy()

        try:
            # Add cover art URL
            if album.get("mbid"):
                enhanced["cover_art_url"] = (
                    f"https://coverartarchive.org/release/{album['mbid']}/front-250"
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
            # Get approved recommendations
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

                        # Add to recently added (for the ribbon)
                        if self.stats_tracker:
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
