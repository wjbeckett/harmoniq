# src/harmoniq/plex_client.py
import logging
import time
import random
from datetime import datetime, timedelta
import pytz

from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized, BadRequest, PlexApiException
from plexapi.playlist import Playlist
from plexapi.library import LibrarySection
from plexapi.audio import Track as PlexApiTrack

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

    def _apply_common_filters(self, tracks: list[PlexApiTrack]) -> list[PlexApiTrack]:
        """Helper function to apply rating, recency, and skip filters."""
        if not tracks:
            return []
            
        logger.debug(f"Applying common filters to {len(tracks)} tracks...")
        filtered_tracks = []
        min_rating_stars = config.TIME_PLAYLIST_MIN_RATING
        
        exclude_cutoff_date = None
        if config.TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS > 0:
            try:
                current_timezone = pytz.timezone(config.TIMEZONE)
                now_aware = datetime.now(current_timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone '{config.TIMEZONE}' for recency filter, using UTC.")
                now_aware = datetime.now(pytz.utc)
            exclude_cutoff_date = now_aware - timedelta(days=config.TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS)
            logger.debug(f"Recency filter: Excluding tracks played since {exclude_cutoff_date.strftime('%Y-%m-%d') if exclude_cutoff_date else 'N/A'}")

        max_skips = config.TIME_PLAYLIST_MAX_SKIP_COUNT

        for track in tracks:
            # Rating check
            if min_rating_stars > 0:
                user_rating_plex = track.userRating if hasattr(track, 'userRating') else None
                if user_rating_plex is None: pass # Keep unrated
                else:
                    user_rating_stars = user_rating_plex / 2.0
                    if user_rating_stars < min_rating_stars:
                        logger.debug(f"Excluding (Rating): '{track.title}' (Rated: {user_rating_stars:.1f} < Min: {min_rating_stars} stars)")
                        continue
            
            # Recency check
            if exclude_cutoff_date and track.lastViewedAt:
                # Ensure track.lastViewedAt is timezone-aware
                # Plex stores datetimes as naive UTC, so localize to UTC then convert.
                try:
                    track_last_played_aware = track.lastViewedAt.replace(tzinfo=pytz.utc).astimezone(exclude_cutoff_date.tzinfo)
                    if track_last_played_aware >= exclude_cutoff_date:
                        logger.debug(f"Excluding (Recency): '{track.title}' (Last played: {track_last_played_aware.strftime('%Y-%m-%d')})")
                        continue
                except Exception as tz_err:
                    logger.warning(f"Could not perform timezone conversion for recency check on track '{track.title}': {tz_err}")

            
            # Skip count check
            skip_count = track.skipCount if hasattr(track, 'skipCount') and track.skipCount is not None else 0
            if skip_count > max_skips:
                logger.debug(f"Excluding (Skips): '{track.title}' (Skips: {skip_count} > {max_skips})")
                continue
            
            filtered_tracks.append(track)
        logger.debug(f"{len(filtered_tracks)} tracks remaining after common filters.")
        return filtered_tracks
    
    def _similarity_score(self, current_track: PlexApiTrack, candidate_track: PlexApiTrack,
                          limit: int, max_distance: float) -> int:
        """Calculates a similarity score (lower is better, like an index)."""
        try:
            # Add a small delay to be extremely cautious with Plex server load
            time.sleep(0.05) # 50ms delay
            similars = current_track.sonicallySimilar(limit=limit, maxDistance=max_distance)
            for index, similar_track in enumerate(similars):
                if similar_track.ratingKey == candidate_track.ratingKey:
                    return index # Lower index means more similar
            return limit + 1 # Not found within the limited similar list, assign a high score
        except PlexApiException as e:
            logger.warning(f"Could not get sonic similarity for '{current_track.title}' (vs '{candidate_track.title}'): {e}. Assigning max score.")
            return limit + 2 # Even higher score if API error
        except Exception as e:
            logger.error(f"Unexpected error calculating similarity for '{current_track.title}': {e}. Assigning max score.")
            return limit + 3

    def _sort_by_sonic_similarity_greedy(self, tracks_to_sort: list[PlexApiTrack],
                                         score_limit: int, score_max_distance: float) -> list[PlexApiTrack]:
        """Sorts a list of tracks using a greedy sonic similarity algorithm."""
        if len(tracks_to_sort) < 2:
            return tracks_to_sort

        logger.info(f"Performing greedy sonic sort on {len(tracks_to_sort)} tracks...")
        remaining_tracks = list(tracks_to_sort) # Make a mutable copy
        sorted_playlist = []

        # Start with a random track
        current_track = random.choice(remaining_tracks)
        sorted_playlist.append(current_track)
        remaining_tracks.remove(current_track)
        logger.debug(f"Sonic sort starting with: '{current_track.title}'")

        while remaining_tracks:
            # Find the track in remaining_tracks most similar to current_track
            best_candidate = None
            lowest_score = float('inf')

            if len(remaining_tracks) % 10 == 0 or len(remaining_tracks) == 1 : # Log progress occasionally
                 logger.debug(f"Sonic sort: {len(remaining_tracks)} tracks remaining to sort.")

            for candidate_track in remaining_tracks:
                score = self._similarity_score(current_track, candidate_track, score_limit, score_max_distance)
                if score < lowest_score:
                    lowest_score = score
                    best_candidate = candidate_track
            
            if best_candidate:
                logger.debug(f"Next track in sonic sort: '{best_candidate.title}' (Score: {lowest_score} from '{current_track.title}')")
                sorted_playlist.append(best_candidate)
                remaining_tracks.remove(best_candidate)
                current_track = best_candidate # Move to the newly added track
            else:
                # Should not happen if remaining_tracks is not empty, but as a fallback:
                logger.warning("Sonic sort: Could not find a best candidate. Appending remaining tracks randomly.")
                random.shuffle(remaining_tracks)
                sorted_playlist.extend(remaining_tracks)
                break
        
        logger.info(f"Greedy sonic sort complete. Sorted {len(sorted_playlist)} tracks.")
        return sorted_playlist

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
        logger.info(f"Refinement settings: MinRatingStars={config.TIME_PLAYLIST_MIN_RATING}, ExcludePlayedDays={config.TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS}, MaxSkipCount={config.TIME_PLAYLIST_MAX_SKIP_COUNT}")
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION:
            logger.info(f"Sonic Expansion: Enabled (Seeds={config.TIME_PLAYLIST_SONIC_SEED_TRACKS}, PerSeed={config.TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED}, MaxDist={config.TIME_PLAYLIST_SONIC_MAX_DISTANCE}, MixRatio={config.TIME_PLAYLIST_FINAL_MIX_RATIO})")
        
        initial_candidate_tracks_mood_genre = []
        all_fetched_rating_keys = set()

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
                MAX_FETCH_MOOD_GENRE = limit * 10 # Increased pool
                tracks_from_plex = library.search(libtype='track', limit=MAX_FETCH_MOOD_GENRE, filters=plex_filters)
                logger.debug(f"Found {len(tracks_from_plex)} tracks initially matching mood/genre in '{library.title}'.")
                for track in tracks_from_plex:
                    if track.ratingKey not in all_fetched_rating_keys:
                        initial_candidate_tracks_mood_genre.append(track)
                        all_fetched_rating_keys.add(track.ratingKey)
            except BadRequest as e: logger.error(f"BadRequest searching by mood/genre in '{library.title}': {e}.")
            except Exception as e: logger.exception(f"Unexpected error searching by mood/genre in '{library.title}': {e}")
        
        logger.info(f"Found {len(initial_candidate_tracks_mood_genre)} total unique candidate tracks from mood/genre search.")

        refined_mood_genre_tracks = self._apply_common_filters(initial_candidate_tracks_mood_genre)
        logger.info(f"{len(refined_mood_genre_tracks)} tracks remaining after applying common filters to mood/genre pool.")

        sonically_expanded_pool_filtered = []
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and refined_mood_genre_tracks:
            logger.info("Sonic expansion enabled. Selecting seed tracks...")
            
            num_seeds = min(config.TIME_PLAYLIST_SONIC_SEED_TRACKS, len(refined_mood_genre_tracks))
            if num_seeds > 0:
                seed_tracks = random.sample(refined_mood_genre_tracks, k=num_seeds)
                logger.info(f"Selected {len(seed_tracks)} seed tracks for sonic expansion.")

                current_playlist_candidate_keys = set(t.ratingKey for t in refined_mood_genre_tracks)

                temp_sonic_candidates = []
                for i, seed_track in enumerate(seed_tracks):
                    logger.debug(f"Fetching sonically similar for seed {i+1}/{num_seeds}: '{seed_track.title}' by '{seed_track.artist().title if seed_track.artist() else 'N/A'}'")
                    try:
                        time.sleep(0.1)
                        similar = seed_track.sonicallySimilar(
                            limit=config.TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED,
                            maxDistance=config.TIME_PLAYLIST_SONIC_MAX_DISTANCE
                        )
                        logger.debug(f"Found {len(similar)} raw sonically similar tracks for '{seed_track.title}'.")
                        for s_track in similar:
                            if s_track.ratingKey not in current_playlist_candidate_keys:
                                temp_sonic_candidates.append(s_track)
                                current_playlist_candidate_keys.add(s_track.ratingKey)
                    except PlexApiException as e: logger.warning(f"Could not get sonically similar for '{seed_track.title}': {e}")
                    except Exception as e: logger.exception(f"Error fetching sonically similar for '{seed_track.title}': {e}")
                
                logger.info(f"Collected {len(temp_sonic_candidates)} initial unique sonically similar tracks (before filtering).")
                sonically_expanded_pool_filtered = self._apply_common_filters(temp_sonic_candidates)
                logger.info(f"{len(sonically_expanded_pool_filtered)} sonically similar tracks remaining after common filters.")
            else:
                logger.info("Not enough refined mood/genre tracks to select seeds for sonic expansion.")

        final_candidate_pool = list(refined_mood_genre_tracks)
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and sonically_expanded_pool_filtered:
            num_mood_genre_current = len(final_candidate_pool); num_sonic_to_add = 0
            if 0.0 < config.TIME_PLAYLIST_FINAL_MIX_RATIO < 1.0:
                target_sonic_count = int(limit * config.TIME_PLAYLIST_FINAL_MIX_RATIO)
                target_mood_genre_count = limit - target_sonic_count
                if len(final_candidate_pool) > target_mood_genre_count: final_candidate_pool = random.sample(final_candidate_pool, k=target_mood_genre_count)
                num_mood_genre_current = len(final_candidate_pool)
                num_sonic_to_add = min(len(sonically_expanded_pool_filtered), limit - num_mood_genre_current, target_sonic_count)
            else: num_sonic_to_add = min(len(sonically_expanded_pool_filtered), limit - num_mood_genre_current)
            if num_sonic_to_add > 0:
                sonic_additions = random.sample(sonically_expanded_pool_filtered, k=num_sonic_to_add)
                final_candidate_pool.extend(sonic_additions); logger.info(f"Added {len(sonic_additions)} sonically similar tracks to the pool.")
        elif not refined_mood_genre_tracks and sonically_expanded_pool_filtered:
            logger.info("Only sonically expanded tracks available (mood/genre pool was empty after filtering).")
            final_candidate_pool = sonically_expanded_pool_filtered
        
        if not final_candidate_pool: logger.warning("No tracks remaining after all filtering and sonic expansion (if enabled)."); return []
        
        # Ensure unique tracks before final limit and sort
        final_tracks_dict = {track.ratingKey: track for track in final_candidate_pool}
        unique_final_tracks = list(final_tracks_dict.values())
        
        # Limit the pool *before* expensive sorting if it's too large
        if len(unique_final_tracks) > limit * 1.5: # Sort a slightly larger pool then limit
             logger.debug(f"Pre-sort pool size {len(unique_final_tracks)}, sampling down before sort to ~{int(limit*1.2)}")
             unique_final_tracks = random.sample(unique_final_tracks, k=int(limit*1.2))

        if config.TIME_PLAYLIST_SONIC_SORT and len(unique_final_tracks) > 1:
            selected_tracks_before_sort = unique_final_tracks
            # Use the new config vars for sorting parameters
            selected_tracks = self._sort_by_sonic_similarity_greedy(
                unique_final_tracks,
                score_limit=config.TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT,
                score_max_distance=config.TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE
            )
            # The sort function returns the full sorted list, limiting happens after.
        else:
            # If not sorting, just shuffle the unique tracks
            random.shuffle(unique_final_tracks)
            selected_tracks = unique_final_tracks
        
        # Final limit
        k = min(limit, len(selected_tracks))
        final_selected_tracks = selected_tracks[:k]
        
        logger.info(f"Selected {len(final_selected_tracks)} tracks for the final time window playlist ({'sonically sorted' if config.TIME_PLAYLIST_SONIC_SORT and len(final_selected_tracks) > 1 else 'randomly selected/shuffled'}).")
        return final_selected_tracks
    
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