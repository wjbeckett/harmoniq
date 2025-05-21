# src/harmoniq/plex_client.py
import logging
import time
import random
from datetime import datetime, timedelta
import pytz
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized, BadRequest
from plexapi.playlist import Playlist
from plexapi.library import LibrarySection

# Import config variables
from . import config

logger = logging.getLogger(__name__)

class PlexClient:
    """Handles interactions with the Plex Media Server."""

    def __init__(self, baseurl=config.PLEX_URL, token=config.PLEX_TOKEN):
        self.baseurl = baseurl
        self.token = token
        self.plex = None
        self._connect()

    def _connect(self):
        """Establishes connection to the Plex server."""
        if not self.baseurl or not self.token:
            logger.error("Plex URL or Token is missing. Cannot connect.")
            raise ValueError("Plex URL or Token is missing.")
        try:
            logger.info(f"Connecting to Plex server at {self.baseurl}...")
            self.plex = PlexServer(self.baseurl, self.token, timeout=30)
            server_name = self.plex.friendlyName
            logger.info(f"Successfully connected to Plex server: {server_name}")
        except Unauthorized:
            logger.error("Plex connection failed: Invalid Plex Token."); self.plex = None; raise
        except NotFound:
            logger.error(f"Plex connection failed: Server not found at {self.baseurl}. Check URL."); self.plex = None; raise
        except Exception as e:
            logger.error(f"An unexpected error occurred connecting to Plex: {e}"); self.plex = None; raise

    def get_music_library(self, library_name: str) -> LibrarySection | None:
        """
        Gets a specific music library object by name from the Plex server.
        Args: library_name: The exact name of the music library section.
        Returns: A plexapi LibrarySection object if found and is a music library, otherwise None.
        """
        if not self.plex: logger.error("Cannot get library: Not connected to Plex."); return None
        if not library_name: logger.error("Cannot get library: No library name provided."); return None
        try:
            logger.debug(f"Attempting to access music library: '{library_name}'")
            music_library = self.plex.library.section(library_name)
            if music_library.type != 'artist': # Check if it's actually a music library
                 logger.warning(f"Section '{library_name}' is not a Music library (type: {music_library.type}). Skipping.")
                 return None
            logger.debug(f"Successfully accessed library '{music_library.title}'.")
            return music_library
        except NotFound:
            logger.warning(f"Music library '{library_name}' not found on the Plex server.")
            return None
        except Exception as e:
            logger.error(f"An error occurred accessing library '{library_name}': {e}")
            return None

    def find_track(self, music_libraries: list[LibrarySection], artist_name: str, track_title: str):
        """
        Searches for a specific track sequentially across multiple music libraries
        using the library's search method with specific filters.
        Args:
            music_libraries: A list of plexapi LibrarySection objects to search within.
            artist_name: The name of the artist.
            track_title: The name of the track.
        """
        if not music_libraries: logger.error("Cannot search track: List of music libraries is empty or invalid."); return None
        if not artist_name or not track_title: logger.warning("Cannot search track: Artist name or track title is missing."); return None

        search_term_log = f"'{artist_name} - {track_title}'"
        logger.debug(f"Searching for track {search_term_log} across {len(music_libraries)} libraries...")

        for library in music_libraries:
            logger.debug(f"Searching in library: '{library.title}'")
            results = []
            try:
                # Using 'artist.title' as the filter field name for the artist.
                logger.debug(f"Attempting exact search with filters: title__iexact='{track_title}', artist.title__iexact='{artist_name}'")
                search_filters_exact = {
                    'title__iexact': track_title,
                    'artist.title__iexact': artist_name # Using dot notation for related field
                }
                results = library.search(libtype='track', filters=search_filters_exact)

                if not results:
                    logger.debug(f"Track not found with exact filter match. Trying broader contains search...")
                    search_filters_broad = {
                        'title__icontains': track_title,
                        'artist.title__icontains': artist_name
                    }
                    results = library.search(libtype='track', filters=search_filters_broad)
                    if not results:
                         logger.debug(f"Track still not found with broader filter search in '{library.title}'.")
                         continue

                if len(results) > 1:
                    found_details = [f"'{t.title}' by '{t.grandparentTitle}' (Album: '{t.parentTitle}')" for t in results[:3]]
                    logger.debug(f"Multiple ({len(results)}) matches found for {search_term_log} in '{library.title}'. Using first: {found_details[0]}. Other matches: {found_details[1:]}")
                track = results[0]
                logger.info(f"Found matching track in '{library.title}': '{track.title}' by '{track.grandparentTitle}' (Key: {track.key})")
                return track
            except BadRequest as e:
                 logger.error(f"BadRequest searching Plex in library '{library.title}' for {search_term_log}: {e}. Filter field 'artist.title' likely incorrect.")
            except Exception as e:
                 logger.exception(f"Unexpected error searching Plex in library '{library.title}' for {search_term_log}: {e}")
        logger.info(f"Track {search_term_log} not found in any library after all searches."); return None

    def find_tracks_by_criteria(self,
                                libraries: list[LibrarySection],
                                moods: list[str] = None,
                                styles: list[str] = None,
                                limit: int = 50):
        """
        Finds tracks across specified libraries matching ANY of the given moods
        AND ANY of the given styles (genres), applying configured refinements
        and potentially expanding with sonically similar tracks.
        """
        if not libraries:
            logger.error("Cannot find tracks by criteria: No libraries provided.")
            return []

        moods_to_match_plex = moods if moods else []
        genres_to_match_plex = styles if styles else []

        logger.info(f"Searching for tracks with Moods: {moods_to_match_plex or 'Any'} AND Genres: {genres_to_match_plex or 'Any'}")
        
        initial_candidate_tracks_mood_genre = []
        all_fetched_rating_keys = set() # Used to avoid adding duplicates from mood/genre search initially

        for library in libraries:
            logger.debug(f"Searching for mood/genre tracks in library: '{library.title}'")
            plex_filters = {}
            if moods_to_match_plex: plex_filters['track.mood'] = moods_to_match_plex
            if genres_to_match_plex: plex_filters['track.genre'] = genres_to_match_plex

            if not plex_filters:
                logger.info(f"No mood or genre criteria for '{library.title}'. Skipping library for mood/genre search.")
                continue
            try:
                logger.debug(f"Plex mood/genre search in '{library.title}' with filters: {plex_filters}")
                # Fetch a larger pool initially based on mood/genre
                MAX_FETCH_MOOD_GENRE = limit * 5 # Fetch more to filter down
                tracks_from_plex = library.search(libtype='track', limit=MAX_FETCH_MOOD_GENRE, filters=plex_filters)
                logger.debug(f"Found {len(tracks_from_plex)} tracks initially matching mood/genre in '{library.title}'.")
                for track in tracks_from_plex:
                    if track.ratingKey not in all_fetched_rating_keys:
                        initial_candidate_tracks_mood_genre.append(track)
                        all_fetched_rating_keys.add(track.ratingKey)
            except BadRequest as e: logger.error(f"BadRequest searching by mood/genre in '{library.title}': {e}.")
            except Exception as e: logger.exception(f"Unexpected error searching by mood/genre in '{library.title}': {e}")
        
        logger.info(f"Found {len(initial_candidate_tracks_mood_genre)} total unique candidate tracks from mood/genre search.")

        # Apply common filters (rating, recency, skips) to the mood/genre pool
        refined_mood_genre_tracks = self._apply_common_filters(initial_candidate_tracks_mood_genre)
        logger.info(f"{len(refined_mood_genre_tracks)} tracks remaining after applying common filters to mood/genre pool.")

        # --- Sonic Expansion Logic ---
        sonically_expanded_pool = []
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and refined_mood_genre_tracks:
            logger.info("Sonic expansion enabled. Selecting seed tracks...")
            
            # Select seed tracks (randomly from the refined mood/genre pool)
            num_seeds = min(config.TIME_PLAYLIST_SONIC_SEED_TRACKS, len(refined_mood_genre_tracks))
            if num_seeds > 0:
                seed_tracks = random.sample(refined_mood_genre_tracks, k=num_seeds)
                logger.info(f"Selected {len(seed_tracks)} seed tracks for sonic expansion.")

                all_sonic_candidates_keys = set(t.ratingKey for t in refined_mood_genre_tracks) # Keep track of keys already in pool or added by sonic

                for i, seed_track in enumerate(seed_tracks):
                    logger.debug(f"Fetching sonically similar tracks for seed {i+1}/{num_seeds}: '{seed_track.title}' by '{seed_track.artist().title}'")
                    try:
                        # Add a small delay to be nice to the Plex server
                        time.sleep(0.1) # 100ms delay before each sonic search
                        similar = seed_track.sonicallySimilar(
                            limit=config.TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED,
                            maxDistance=config.TIME_PLAYLIST_SONIC_MAX_DISTANCE
                        )
                        logger.debug(f"Found {len(similar)} sonically similar tracks for '{seed_track.title}'.")
                        for s_track in similar:
                            if s_track.ratingKey not in all_sonic_candidates_keys:
                                sonically_expanded_pool.append(s_track)
                                all_sonic_candidates_keys.add(s_track.ratingKey) # Add to prevent re-adding
                    except SonicallySimilarError as e: # Catch specific error if sonic data not available
                         logger.warning(f"Could not get sonically similar tracks for '{seed_track.title}': {e}")
                    except Exception as e:
                         logger.exception(f"Error fetching sonically similar for '{seed_track.title}': {e}")
                
                logger.info(f"Collected {len(sonically_expanded_pool)} initial sonically similar tracks (before filtering).")
                # Apply common filters to these newly found sonically similar tracks
                sonically_expanded_pool = self._apply_common_filters(sonically_expanded_pool)
                logger.info(f"{len(sonically_expanded_pool)} sonically similar tracks remaining after common filters.")
            else:
                logger.info("Not enough refined mood/genre tracks to select seeds for sonic expansion.")

        # --- Combine and Select Final Tracks ---
        final_candidate_pool = refined_mood_genre_tracks # Start with the mood/genre tracks
        
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and sonically_expanded_pool:
            num_mood_genre_target = int(limit * (1.0 - config.TIME_PLAYLIST_FINAL_MIX_RATIO))
            num_sonic_target = limit - num_mood_genre_target
            
            logger.info(f"Targeting ~{num_mood_genre_target} mood/genre tracks and ~{num_sonic_target} sonic tracks for final mix.")

            # Take a sample from each pool, respecting targets and availability
            final_mood_genre_sample = random.sample(refined_mood_genre_tracks, k=min(num_mood_genre_target, len(refined_mood_genre_tracks)))
            
            # Ensure sonic tracks are not already in the mood/genre sample
            sonic_pool_for_sampling = [t for t in sonically_expanded_pool if t.ratingKey not in {mg_t.ratingKey for mg_t in final_mood_genre_sample}]
            final_sonic_sample = random.sample(sonic_pool_for_sampling, k=min(num_sonic_target, len(sonic_pool_for_sampling)))
            
            final_candidate_pool = final_mood_genre_sample + final_sonic_sample
            # Shuffle the combined pool for good measure before final limit
            random.shuffle(final_candidate_pool)
            logger.info(f"Combined pool: {len(final_mood_genre_sample)} mood/genre + {len(final_sonic_sample)} sonic = {len(final_candidate_pool)} tracks.")
        
        elif not refined_mood_genre_tracks and sonically_expanded_pool: # Only sonic tracks available
            logger.info("Only sonically expanded tracks available (mood/genre pool was empty after filtering).")
            final_candidate_pool = sonically_expanded_pool
        # Else, final_candidate_pool is just refined_mood_genre_tracks

        if not final_candidate_pool:
            logger.warning("No tracks remaining after all filtering and sonic expansion (if enabled).")
            return []

        # Final deduplication and limit
        final_tracks_dict = {track.ratingKey: track for track in final_candidate_pool}
        unique_final_tracks = list(final_tracks_dict.values())
        
        # Shuffle one last time before limiting
        random.shuffle(unique_final_tracks) 
        
        k = min(limit, len(unique_final_tracks))
        selected_tracks = unique_final_tracks[:k] # Simpler than random.sample if already shuffled
        
        logger.info(f"Selected {len(selected_tracks)} tracks for the final time window playlist.")
        return selected_tracks
    
    def update_playlist(self, playlist_name: str, tracks_to_add: list, music_library: LibrarySection):
        """
        Creates a new Plex playlist or updates an existing one by clearing and adding the provided tracks.
        Args:
            playlist_name: Name of the playlist to create/update.
            tracks_to_add: A list of plexapi.audio.Track objects.
            music_library: The plexapi.library.LibrarySection object to use for context if creating the playlist.
        """
        if not self.plex: logger.error("Cannot update playlist: Not connected to Plex."); return False
        if not playlist_name: logger.error("Cannot update playlist: Playlist name is empty."); return False
        if not music_library: logger.error("Cannot update playlist: Target music library context missing."); return False
        try:
            playlist: Playlist = None
            try:
                logger.debug(f"Checking for existing playlist: '{playlist_name}'")
                playlist = self.plex.playlist(playlist_name)
                logger.info(f"Found existing playlist '{playlist_name}'. Clearing items...")
                if playlist.items(): playlist.removeItems(playlist.items())
                else: logger.debug("Existing playlist empty, no items to clear.")
            except NotFound:
                logger.info(f"Playlist '{playlist_name}' not found. Creating new playlist...")
                if not tracks_to_add: logger.info(f"No tracks to add, skipping creation of empty playlist '{playlist_name}'."); return True
                playlist = self.plex.createPlaylist(playlist_name, section=music_library, items=tracks_to_add)
                logger.info(f"Successfully created playlist '{playlist_name}' in context of library '{music_library.title}' with {len(tracks_to_add)} tracks.")
                return True
            if playlist and tracks_to_add:
                 logger.info(f"Adding {len(tracks_to_add)} tracks to playlist '{playlist_name}'...")
                 playlist.addItems(tracks_to_add)
                 logger.info(f"Successfully updated playlist '{playlist_name}' with {len(tracks_to_add)} tracks.")
                 try:
                     now = time.strftime("%Y-%m-%d %H:%M:%S %Z"); playlist.editSummary(f"Updated by Harmoniq on {now}. Contains {len(tracks_to_add)} tracks.")
                 except Exception as e: logger.warning(f"Could not update summary for playlist '{playlist_name}': {e}")
                 return True
            elif playlist and not tracks_to_add:
                logger.info(f"Playlist '{playlist_name}' exists but has no new tracks to add. Clearing summary if needed or marking as refreshed."); return True
        except BadRequest as e: logger.error(f"BadRequest error updating playlist '{playlist_name}': {e}."); return False
        except Exception as e: logger.exception(f"An unexpected error occurred updating playlist '{playlist_name}': {e}"); return False
        logger.error(f"Reached end of update_playlist for '{playlist_name}' without clear success/failure."); return False