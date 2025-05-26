# src/harmoniq/plex_client.py
import os
import logging
import time
import random
from datetime import datetime, timedelta, timezone
import pytz

from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized, BadRequest, PlexApiException
from plexapi.playlist import Playlist
from plexapi.library import LibrarySection
from plexapi.audio import Track as PlexApiTrack

# Import config variables
from . import config
from collections import Counter
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

    def _apply_common_filters(self, tracks: list[PlexApiTrack], is_historical_track_list: bool = False) -> list[PlexApiTrack]:
        """
        Helper function to apply rating, recency, and skip filters.
        For historical tracks, the recency filter is skipped IF it's their first pass.
        """
        if not tracks: return []
            
        logger.debug(f"Applying common filters to {len(tracks)} tracks (Historical list: {is_historical_track_list})...")
        filtered_tracks = []
        # Use general min rating for non-historical, specific history min rating for historical
        min_rating_stars = config.TIME_PLAYLIST_HISTORY_MIN_RATING if is_historical_track_list else config.TIME_PLAYLIST_MIN_RATING
        
        exclude_cutoff_date = None
        if config.TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS > 0:
            try:
                current_timezone = pytz.timezone(config.TIMEZONE); now_aware = datetime.now(current_timezone)
            except pytz.exceptions.UnknownTimeZoneError: logger.warning(f"Unknown timezone '{config.TIMEZONE}' for recency filter, using UTC."); now_aware = datetime.now(pytz.utc)
            exclude_cutoff_date = now_aware - timedelta(days=config.TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS)
            logger.debug(f"Recency filter: Excluding tracks played since {exclude_cutoff_date.strftime('%Y-%m-%d') if exclude_cutoff_date else 'N/A'}")

        max_skips = config.TIME_PLAYLIST_MAX_SKIP_COUNT

        for track in tracks:
            # Rating check
            if min_rating_stars > 0: # Only apply if a minimum is set
                user_rating_plex = track.userRating if hasattr(track, 'userRating') else None
                if user_rating_plex is None: # Unrated
                    if not is_historical_track_list: pass # Keep unrated for discovery pool
                    # For historical, if min_rating is set, unrated probably shouldn't count as a "favorite" unless min_rating is 0
                    elif is_historical_track_list and min_rating_stars > 0: # If historical and min_rating is set, unrated don't pass
                        logger.debug(f"Excluding (Historical Unrated): '{track.title}' (Min rating for history: {min_rating_stars} stars)")
                        continue
                else: # Rated
                    user_rating_stars = user_rating_plex / 2.0
                    if user_rating_stars < min_rating_stars:
                        logger.debug(f"Excluding (Rating): '{track.title}' (Rated: {user_rating_stars:.1f} < Min: {min_rating_stars} stars)")
                        continue
            
            # Recency check - *always* apply this common filter, even to historical tracks,
            # to avoid adding something that was just played yesterday to the "Daily Flow".
            # The "lookback_days" for fetching historical tracks is different from this "don't play again for X days" filter.
            if exclude_cutoff_date and track.lastViewedAt:
                try:
                    track_last_played_aware = track.lastViewedAt.replace(tzinfo=pytz.utc).astimezone(exclude_cutoff_date.tzinfo)
                    if track_last_played_aware >= exclude_cutoff_date:
                        logger.debug(f"Excluding (Recency): '{track.title}' (Last played: {track_last_played_aware.strftime('%Y-%m-%d')})")
                        continue
                except Exception as tz_err: logger.warning(f"Could not perform timezone conversion for recency check on track '{track.title}': {tz_err}")
            
            # Skip count check
            skip_count = track.skipCount if hasattr(track, 'skipCount') and track.skipCount is not None else 0
            if skip_count > max_skips:
                logger.debug(f"Excluding (Skips): '{track.title}' (Skips: {skip_count} > {max_skips})")
                continue
            
            filtered_tracks.append(track)
        logger.debug(f"{len(filtered_tracks)} tracks remaining after common filters (Historical list: {is_historical_track_list}).")
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

    #### ---- I think this can be removed --- ####
    def _get_historical_favorites(self,
                                 libraries: list[LibrarySection],
                                 moods_to_match: list[str],
                                 genres_to_match: list[str]) -> list[PlexApiTrack]:
        """
        Fetches historical tracks that match current criteria and configured history preferences.
        """
        if not config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS:
            return []

        logger.info(f"Fetching historical favorites: Lookback={config.TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS}d, MinPlays={config.TIME_PLAYLIST_HISTORY_MIN_PLAYS}, MinHistRatingStars={config.TIME_PLAYLIST_HISTORY_MIN_RATING}")
        
        historical_candidates = []
        history_rating_keys = set()
        
        # Ensure lookback_days is positive
        lookback_days = config.TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS
        if lookback_days <= 0:
            logger.debug("History lookback days is not positive, skipping historical fetch.")
            return []

        # Plex history mindate requires a datetime object
        # Server time is UTC, so use UTC for mindate.
        mindate_history = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        for library in libraries:
            logger.debug(f"Fetching history from library: '{library.title}' since {mindate_history.strftime('%Y-%m-%d')}")
            try:
                # .history() can be slow on large libraries if not filtered well by Plex server itself.
                # We fetch, then filter in Python for mood/genre/playcount/rating.
                history_items = library.history(mindate=mindate_history, maxresults=1000) # Limit raw history fetch
                
                for track in history_items:
                    if not isinstance(track, PlexApiTrack): continue # Should only be tracks
                    if track.ratingKey in history_rating_keys: continue # Already processed

                    # 1. Play Count Filter
                    view_count = track.viewCount if hasattr(track, 'viewCount') and track.viewCount is not None else 0
                    if view_count < config.TIME_PLAYLIST_HISTORY_MIN_PLAYS:
                        continue

                    # 2. Rating Filter (for historical tracks)
                    if config.TIME_PLAYLIST_HISTORY_MIN_RATING > 0:
                        user_rating_plex = track.userRating if hasattr(track, 'userRating') else None
                        if user_rating_plex is None: # Unrated historical tracks don't pass if min rating is set
                            continue
                        user_rating_stars = user_rating_plex / 2.0
                        if user_rating_stars < config.TIME_PLAYLIST_HISTORY_MIN_RATING:
                            continue
                    
                    # 3. Mood Filter (track has AT LEAST ONE of the target moods)
                    if moods_to_match: # Only filter if moods are specified for the window
                        track_moods_lower = [m.tag.lower() for m in track.moods] if hasattr(track, 'moods') else []
                        if not any(m.lower() in track_moods_lower for m in moods_to_match):
                            continue
                    
                    # 4. Genre Filter (track has AT LEAST ONE of the target genres)
                    if genres_to_match: # Only filter if genres are specified for the window
                        track_genres_lower = [g.tag.lower() for g in track.genres] if hasattr(track, 'genres') else []
                        if not any(g.lower() in track_genres_lower for g in genres_to_match):
                            continue
                    
                    # If all filters passed
                    logger.debug(f"Found historical candidate: '{track.title}' (Plays: {view_count}, Rating: {track.userRating/2 if track.userRating else 'N/A'})")
                    historical_candidates.append(track)
                    history_rating_keys.add(track.ratingKey)

            except Exception as e:
                logger.exception(f"Error fetching/processing history from library '{library.title}': {e}")

        logger.info(f"Found {len(historical_candidates)} raw historical candidates matching criteria.")
        # The common filters (especially recency) will be applied to these later if they are chosen
        return historical_candidates

    def _get_tracks_matching_mood_genre_style(self, library: LibrarySection, 
                                             moods_to_match: list[str], 
                                             genres_or_styles_to_match: list[str],
                                             fetch_limit: int) -> list[PlexApiTrack]:
        """
        Helper to search a library for tracks matching moods AND (genres OR styles).
        This incorporates the idea of searching genres OR styles for the user's terms.
        """
        candidate_tracks_for_lib = []
        temp_keys_in_lib = set()

        plex_filters_mood = {}
        if moods_to_match:
            plex_filters_mood['track.mood'] = moods_to_match
        
        # Search 1: Moods AND Genres
        if genres_or_styles_to_match:
            current_filters_genre = plex_filters_mood.copy()
            current_filters_genre['track.genre'] = genres_or_styles_to_match
            logger.debug(f"Searching '{library.title}' with Moods+Genres filters: {current_filters_genre}")
            try:
                tracks = library.search(libtype='track', limit=fetch_limit, filters=current_filters_genre)
                for track in tracks:
                    if track.ratingKey not in temp_keys_in_lib:
                        candidate_tracks_for_lib.append(track)
                        temp_keys_in_lib.add(track.ratingKey)
                logger.debug(f"Found {len(tracks)} tracks via Moods+Genres in '{library.title}'.")
            except BadRequest as e: logger.warning(f"BadRequest on Moods+Genres search in '{library.title}': {e}")
            except Exception as e: logger.exception(f"Error on Moods+Genres search in '{library.title}': {e}")

        # Search 2: Moods AND Styles (if styles are distinct from genres in your Plex setup)
        # We need to ensure Sonic Analysis populates 'track.style' for this to be effective.
        # If user terms in genres_or_styles_to_match are meant for 'track.style'
        if genres_or_styles_to_match: # Re-using genres_or_styles_to_match for 'track.style'
            current_filters_style = plex_filters_mood.copy()
            current_filters_style['track.style'] = genres_or_styles_to_match # Use 'track.style'
            logger.debug(f"Searching '{library.title}' with Moods+Styles filters: {current_filters_style}")
            try:
                tracks = library.search(libtype='track', limit=fetch_limit, filters=current_filters_style)
                for track in tracks:
                    if track.ratingKey not in temp_keys_in_lib:
                        candidate_tracks_for_lib.append(track)
                        temp_keys_in_lib.add(track.ratingKey)
                logger.debug(f"Found {len(tracks)} tracks via Moods+Styles in '{library.title}'.")
            except BadRequest as e: logger.warning(f"BadRequest on Moods+Styles search in '{library.title}': {e}") # track.style might not be a valid filter key for all servers/versions
            except Exception as e: logger.exception(f"Error on Moods+Styles search in '{library.title}': {e}")
            
        # Fallback: If only moods specified, or if both genre and style searches yield nothing with moods
        if not candidate_tracks_for_lib and moods_to_match and not genres_or_styles_to_match:
            logger.debug(f"Searching '{library.title}' with Moods-only filters: {plex_filters_mood}")
            try:
                tracks = library.search(libtype='track', limit=fetch_limit, filters=plex_filters_mood)
                for track in tracks: # Duplicates will be handled later
                    if track.ratingKey not in temp_keys_in_lib:
                        candidate_tracks_for_lib.append(track)
                        temp_keys_in_lib.add(track.ratingKey)
                logger.debug(f"Found {len(tracks)} tracks via Moods-only in '{library.title}'.")
            except BadRequest as e: logger.warning(f"BadRequest on Moods-only search in '{library.title}': {e}")
            except Exception as e: logger.exception(f"Error on Moods-only search in '{library.title}': {e}")

        return candidate_tracks_for_lib


    def _select_vibe_anchors(self, libraries: list[LibrarySection], 
                            target_moods: list[str], target_styles: list[str], # target_styles are genres_or_styles
                            count: int) -> list[PlexApiTrack]:
        logger.info(f"Selecting {count} Vibe Anchors: Moods={target_moods}, Styles/Genres={target_styles}")
        candidate_anchors = []
        fetch_limit_per_lib = count * 5 # Fetch more initially

        for lib in libraries:
            tracks = self._get_tracks_matching_mood_genre_style(lib, target_moods, target_styles, fetch_limit_per_lib)
            candidate_anchors.extend(tracks)
        
        # Deduplicate across libraries
        unique_candidates = list({t.ratingKey: t for t in candidate_anchors}.values())
        logger.info(f"Found {len(unique_candidates)} unique Vibe Anchor candidates initially.")

        # Apply common filters (using general discovery rating, recency, skips)
        filtered_anchors = self._apply_common_filters(unique_candidates, is_historical_track_list=False)
        logger.info(f"{len(filtered_anchors)} Vibe Anchors remaining after common filters.")

        if not filtered_anchors: return []
        
        # Select 'count' best (e.g., random for now, could be highest rated)
        random.shuffle(filtered_anchors)
        return filtered_anchors[:count]


    def _get_raw_historical_tracks_for_period_hours(self, libraries: list[LibrarySection],
                                                    lookback_days: int,
                                                    period_active_hours: set[int]
                                                    ) -> list[PlexApiTrack]:
        logger.info(f"Fetching raw play history for period hours: {sorted(list(period_active_hours))}, Lookback: {lookback_days}d")
        
        raw_historical_tracks_matching_hours = []
        all_history_fetched_count = 0
        processed_keys_for_hour_match = set() # Tracks keys that have been added to the list

        if lookback_days <= 0: 
            logger.debug("History lookback days is not positive, skipping historical fetch.")
            return []
        
        # mindate for history is UTC
        mindate_history = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        for library in libraries: # Iterate through user's specified music libraries
            logger.debug(f"Fetching all history from library '{library.title}' since {mindate_history.strftime('%Y-%m-%d')} (maxresults=5000)")
            try:
                # Get history items from the specific library
                history_items_raw = library.history(mindate=mindate_history, maxresults=5000)
                all_history_fetched_count += len(history_items_raw)
                logger.debug(f"Plex library.history() returned {len(history_items_raw)} raw items for '{library.title}'.")

                if not history_items_raw:
                    continue

                for i, history_entry_stub in enumerate(history_items_raw):
                    actual_track_object = None
                    # The items from .history() might be the Track object directly, or a PlayHistory object
                    if isinstance(history_entry_stub, PlexApiTrack):
                        actual_track_object = history_entry_stub
                    elif hasattr(history_entry_stub, 'track') and isinstance(history_entry_stub.track, PlexApiTrack):
                        actual_track_object = history_entry_stub.track
                    elif hasattr(history_entry_stub, 'item') and isinstance(history_entry_stub.item, PlexApiTrack):
                        actual_track_object = history_entry_stub.item
                    
                    if not actual_track_object:
                        logger.warning(f"Item {i} in history for '{library.title}' not a recognizable Track or PlayHistory. Type: {type(history_entry_stub)}")
                        continue

                    # --- Fetch the FULL track object using its ratingKey to get all attributes ---
                    # The `actual_track_object` from history might be partial.
                    # Re-fetch from the server using its ratingKey.
                    # self.plex is the PlexServer instance.
                    try:
                        logger.debug(f"Fetching full metadata for history track: '{actual_track_object.title}' (RatingKey: {actual_track_object.ratingKey})")
                        full_track_object = self.plex.fetchItem(actual_track_object.ratingKey)
                        if not isinstance(full_track_object, PlexApiTrack):
                            logger.warning(f"Fetched item for key {actual_track_object.ratingKey} is not a Track. Skipping.")
                            continue
                        # Now use full_track_object for attribute checks
                        track_to_check = full_track_object 
                    except Exception as fetch_err:
                        logger.warning(f"Could not fetch full track object for key {actual_track_object.ratingKey} ('{actual_track_object.title}'): {fetch_err}. Using potentially partial data from history.")
                        track_to_check = actual_track_object # Fallback to the potentially partial object
                    # --- End of full track object fetch ---

                    logger.debug(f"Processing history track [{i+1}/{len(history_items_raw)}]: '{track_to_check.title}', LastViewed: {track_to_check.lastViewedAt}, ViewCount: {track_to_check.viewCount}, UserRating: {track_to_check.userRating}")

                    if track_to_check.ratingKey in processed_keys_for_hour_match: continue
                    
                    if track_to_check.lastViewedAt: # Check lastViewedAt on the (hopefully) full object
                        try:
                            user_tz = pytz.timezone(config.TIMEZONE)
                            played_time_utc = track_to_check.lastViewedAt.replace(tzinfo=pytz.utc)
                            played_time_local = played_time_utc.astimezone(user_tz)
                            logger.debug(f"  '{track_to_check.title}' - PlayedAt (UTC): {played_time_utc}, PlayedAt (Local {config.TIMEZONE}): {played_time_local}, LocalHour: {played_time_local.hour}")
                            if played_time_local.hour in period_active_hours:
                                logger.debug(f"    --> MATCHED HOUR: '{track_to_check.title}' (Hour: {played_time_local.hour}) added.")
                                raw_historical_tracks_matching_hours.append(track_to_check) # Add the full object
                                processed_keys_for_hour_match.add(track_to_check.ratingKey)
                        except pytz.exceptions.UnknownTimeZoneError:
                            logger.error(f"  Unknown timezone '{config.TIMEZONE}' for '{track_to_check.title}'. Comparing UTC hour.")
                            if track_to_check.lastViewedAt.hour in period_active_hours: # Fallback
                                logger.debug(f"    --> MATCHED HOUR (UTC Fallback): '{track_to_check.title}' (Hour: {track_to_check.lastViewedAt.hour})")
                                raw_historical_tracks_matching_hours.append(track_to_check)
                                processed_keys_for_hour_match.add(track_to_check.ratingKey)
                        except Exception as e_tz: logger.warning(f"  Error processing tz for '{track_to_check.title}': {e_tz}")
                    else:
                        logger.debug(f"  Track '{track_to_check.title}' has no lastViewedAt attribute (even after attempting full fetch). Skipping for hour check.")
            except Exception as e:
                logger.exception(f"Error processing history items from library '{library.title}': {e}")
            
            logger.info(f"Total items fetched directly from Plex history endpoint for all libraries: {all_history_fetched_count}")
            logger.info(f"Found {len(raw_historical_tracks_matching_hours)} raw historical plays matching period hours (after full object fetch & Python-side hour filtering).")
            return raw_historical_tracks_matching_hours

    def _is_vibe_compatible(self, track_moods_lower: list[str], track_genres_lower: list[str], 
                        target_moods: list[str], target_genres_or_styles: list[str]) -> bool:
        """Checks if a track is loosely compatible with the target vibe."""
        if not target_moods and not target_genres_or_styles: return True # No target, so compatible

        mood_match = False
        if target_moods:
            if any(m.lower() in track_moods_lower for m in target_moods):
                mood_match = True
        else: # No mood target, so consider mood aspect matched
            mood_match = True 
            
        genre_style_match = False
        if target_genres_or_styles:
            # Check against track's genres
            if any(g.lower() in track_genres_lower for g in target_genres_or_styles):
                genre_style_match = True
            # Optionally, also check against track's styles if distinct and available
            # track_styles_lower = [s.tag.lower() for s in track.styles] if hasattr(track, 'styles') else []
            # if any(s.lower() in track_styles_lower for s in target_genres_or_styles):
            #    genre_style_match = True
        else: # No genre/style target, so consider this aspect matched
            genre_style_match = True
            
        return mood_match and genre_style_match


    def _select_familiar_anchors(self, 
                            # libraries: list[LibrarySection], # No longer needs libraries
                            target_moods: list[str], 
                            target_styles: list[str], 
                            count: int, 
                            # period_active_hours: set[int], # No longer needs hours
                            historical_tracks_for_period: list[PlexApiTrack] # Receives pre-fetched tracks
                            ) -> list[PlexApiTrack]:
        logger.info(f"Selecting {count} Familiar Anchors from {len(historical_tracks_for_period)} provided historical tracks.")
        
        if not config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS or not historical_tracks_for_period:
            return []

        compatible_historical_favorites = []
        for track in historical_tracks_for_period: # Already filtered by hour and lookback
            view_count = track.viewCount if hasattr(track, 'viewCount') else 0
            if view_count < config.TIME_PLAYLIST_HISTORY_MIN_PLAYS: continue
            if config.TIME_PLAYLIST_HISTORY_MIN_RATING > 0:
                user_rating_plex = track.userRating if hasattr(track, 'userRating') else None
                if user_rating_plex is None: continue
                user_rating_stars = user_rating_plex / 2.0
                if user_rating_stars < config.TIME_PLAYLIST_HISTORY_MIN_RATING: continue
            
            track_moods_l = [m.tag.lower() for m in track.moods] if hasattr(track, 'moods') else []
            track_genres_l = [g.tag.lower() for g in track.genres] if hasattr(track, 'genres') else []
            if not self._is_vibe_compatible(track_moods_l, track_genres_l, target_moods, target_styles):
                logger.debug(f"Historical track '{track.title}' not vibe-compatible with target. Skipping for familiar anchor.")
                continue
            compatible_historical_favorites.append(track)

        logger.info(f"Found {len(compatible_historical_favorites)} vibe-compatible historical tracks after play/rating filters (from provided list).")
        filtered_anchors = self._apply_common_filters(compatible_historical_favorites, is_historical_track_list=True)
        logger.info(f"{len(filtered_anchors)} Familiar Anchors remaining after common filters.")
        if not filtered_anchors: return []
        random.shuffle(filtered_anchors)
        return filtered_anchors[:count]

    def find_tracks_by_criteria(self,
                                libraries: list[LibrarySection],
                                moods: list[str] = None,
                                styles: list[str] = None, # Treated as genres
                                limit: int = config.PLAYLIST_SIZE_TIME): # Use config for default
        """
        Finds tracks across specified libraries matching ANY of the given moods
        AND ANY of the given styles (genres), applying configured refinements
        and potentially expanding with sonically similar tracks.
        """
        # Ensure limit is positive, fallback if config somehow allows non-positive
        actual_limit = limit if limit > 0 else 40 
        if limit <= 0 :
            logger.warning(f"Configured limit for time playlist ({limit}) is not positive. Defaulting to 40.")

        if not libraries:
            logger.error("Cannot find tracks by criteria: No libraries provided.")
            return []

        moods_to_match = moods if moods else [] 
        genres_to_match = styles if styles else [] 

        logger.info(f"Searching for tracks with Moods: {moods_to_match or 'Any'} AND Genres: {genres_to_match or 'Any'}")
        logger.info(f"Targeting up to {actual_limit} tracks for the playlist.") # Log the actual limit being used
        logger.info(f"Refinement settings: MinRatingStars={config.TIME_PLAYLIST_MIN_RATING}, ExcludePlayedDays={config.TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS}, MaxSkipCount={config.TIME_PLAYLIST_MAX_SKIP_COUNT}")
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION:
            logger.info(f"Sonic Expansion: Enabled (Seeds={config.TIME_PLAYLIST_SONIC_SEED_TRACKS}, PerSeed={config.TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED}, MaxDist={config.TIME_PLAYLIST_SONIC_MAX_DISTANCE}, MixRatio={config.TIME_PLAYLIST_FINAL_MIX_RATIO})")
        if config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS:
            logger.info(f"History Integration: Enabled (Lookback={config.TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS}d, MinPlays={config.TIME_PLAYLIST_HISTORY_MIN_PLAYS}, MinHistRating={config.TIME_PLAYLIST_HISTORY_MIN_RATING}*, TargetCount={config.TIME_PLAYLIST_TARGET_HISTORY_COUNT})")

        # 1. Fetch Historical Favorites
        historical_favorites = []
        if config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS:
            historical_favorites = self._get_historical_favorites(libraries, moods_to_match, genres_to_match)
            historical_favorites = self._apply_common_filters(historical_favorites, is_historical_track_list=True)
            logger.info(f"{len(historical_favorites)} historical favorites remaining after common filters.")

        # 2. Fetch Mood/Genre Tracks (Discovery Pool)
        initial_candidate_tracks_mood_genre = []
        all_mood_genre_keys = set(t.ratingKey for t in historical_favorites) 
        for library in libraries:
            logger.debug(f"Searching for mood/genre tracks in library: '{library.title}'")
            plex_filters = {}
            if moods_to_match: plex_filters['track.mood'] = moods_to_match
            if genres_to_match: plex_filters['track.genre'] = genres_to_match
            if not plex_filters: logger.info(f"No mood or genre criteria for '{library.title}'. Skipping."); continue
            try:
                logger.debug(f"Plex mood/genre search in '{library.title}' with filters: {plex_filters}")
                MAX_FETCH_MOOD_GENRE = (actual_limit + config.TIME_PLAYLIST_TARGET_HISTORY_COUNT) * 10
                tracks_from_plex = library.search(libtype='track', limit=MAX_FETCH_MOOD_GENRE, filters=plex_filters)
                logger.debug(f"Found {len(tracks_from_plex)} tracks initially matching mood/genre in '{library.title}'.")
                for track in tracks_from_plex:
                    if track.ratingKey not in all_mood_genre_keys:
                        initial_candidate_tracks_mood_genre.append(track)
                        all_mood_genre_keys.add(track.ratingKey)
            except BadRequest as e: logger.error(f"BadRequest searching by mood/genre in '{library.title}': {e}.")
            except Exception as e: logger.exception(f"Unexpected error searching by mood/genre in '{library.title}': {e}")
        logger.info(f"Found {len(initial_candidate_tracks_mood_genre)} unique new candidate tracks from mood/genre search.")
        refined_mood_genre_tracks = self._apply_common_filters(initial_candidate_tracks_mood_genre, is_historical_track_list=False)
        logger.info(f"{len(refined_mood_genre_tracks)} new mood/genre tracks remaining after common filters.")

        # 3. Sonic Expansion
        sonically_expanded_pool_filtered = []
        combined_seed_pool = list(historical_favorites) + list(refined_mood_genre_tracks)
        random.shuffle(combined_seed_pool)
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and combined_seed_pool:
            logger.info("Sonic expansion enabled. Selecting seed tracks from combined pool...")
            num_seeds = min(config.TIME_PLAYLIST_SONIC_SEED_TRACKS, len(combined_seed_pool))
            if num_seeds > 0:
                seed_tracks = random.sample(combined_seed_pool, k=num_seeds)
                logger.info(f"Selected {len(seed_tracks)} seed tracks for sonic expansion.")
                current_playlist_candidate_keys = set(t.ratingKey for t in combined_seed_pool)
                temp_sonic_candidates = []
                for i, seed_track in enumerate(seed_tracks):
                    logger.debug(f"Fetching sonically similar for seed {i+1}/{num_seeds}: '{seed_track.title}' by '{seed_track.artist().title if seed_track.artist() else 'N/A'}'")
                    try:
                        time.sleep(0.1)
                        similar = seed_track.sonicallySimilar(limit=config.TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED, maxDistance=config.TIME_PLAYLIST_SONIC_MAX_DISTANCE)
                        logger.debug(f"Found {len(similar)} raw sonically similar tracks for '{seed_track.title}'.")
                        for s_track in similar:
                            if s_track.ratingKey not in current_playlist_candidate_keys:
                                temp_sonic_candidates.append(s_track)
                                current_playlist_candidate_keys.add(s_track.ratingKey)
                    except PlexApiException as e: logger.warning(f"Could not get sonically similar for '{seed_track.title}' (PlexApiException): {e}")
                    except Exception as e: logger.exception(f"Unexpected error fetching sonically similar for '{seed_track.title}': {e}")
                logger.info(f"Collected {len(temp_sonic_candidates)} initial unique sonically similar tracks (before filtering).")
                sonically_expanded_pool_filtered = self._apply_common_filters(temp_sonic_candidates, is_historical_track_list=False)
                logger.info(f"{len(sonically_expanded_pool_filtered)} sonically similar tracks remaining after common filters.")
            else: logger.info("Not enough tracks in combined pool to select seeds for sonic expansion.")

        # 4. Combine, Prioritize History, and Select Final Tracks
        final_candidate_pool = []
        num_history_added = 0
        if config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS and historical_favorites:
            # Shuffle historical favorites before picking to vary which ones get priority if more than target
            random.shuffle(historical_favorites) 
            for hist_track in historical_favorites:
                if len(final_candidate_pool) < config.TIME_PLAYLIST_TARGET_HISTORY_COUNT:
                    final_candidate_pool.append(hist_track)
                    # num_history_added += 1 # Already tracked by len(final_candidate_pool) in this section
                else: break
            logger.info(f"Added {len(final_candidate_pool)} prioritized historical tracks to the pool.")

        # Combine remaining pools (refined mood/genre + filtered sonic)
        remaining_discovery_pool = []
        # Use a set for efficient checking of already added historical tracks' keys
        added_keys = set(t.ratingKey for t in final_candidate_pool) 

        for track in refined_mood_genre_tracks:
            if track.ratingKey not in added_keys:
                remaining_discovery_pool.append(track)
                added_keys.add(track.ratingKey) # Add to set as it's now considered for this pool
        
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and sonically_expanded_pool_filtered:
            for track in sonically_expanded_pool_filtered:
                if track.ratingKey not in added_keys:
                    remaining_discovery_pool.append(track)
                    added_keys.add(track.ratingKey)
        
        random.shuffle(remaining_discovery_pool)
        
        num_needed_from_discovery = actual_limit - len(final_candidate_pool)
        if num_needed_from_discovery > 0 and remaining_discovery_pool:
            final_candidate_pool.extend(remaining_discovery_pool[:num_needed_from_discovery])
        
        logger.info(f"Combined pool size before sort/final limit: {len(final_candidate_pool)}")
        if not final_candidate_pool: logger.warning("No tracks remaining after all filtering and expansion."); return []
        
        # Deduplicate one last time (primarily if history + discovery had overlaps not caught by key sets)
        final_tracks_dict = {track.ratingKey: track for track in final_candidate_pool}
        unique_final_tracks = list(final_tracks_dict.values())

        # Limit the pool for sorting if it's still much larger than needed
        if len(unique_final_tracks) > actual_limit * 1.5: 
            logger.debug(f"Pre-sort pool size {len(unique_final_tracks)}, sampling down before sort to ~{int(actual_limit*1.2)}")
            unique_final_tracks = random.sample(unique_final_tracks, k=int(actual_limit*1.2))

        # Apply Sonic Sort if enabled
        if config.TIME_PLAYLIST_SONIC_SORT and len(unique_final_tracks) > 1:
            selected_tracks = self._sort_by_sonic_similarity_greedy(
                unique_final_tracks,
                score_limit=config.TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT,
                score_max_distance=config.TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE
            )
        else:
            random.shuffle(unique_final_tracks) # Shuffle if not sonically sorting
            selected_tracks = unique_final_tracks
        
        # Final limit to the desired playlist size
        final_k = min(actual_limit, len(selected_tracks))
        final_selected_tracks = selected_tracks[:final_k]
        
        logger.info(f"Selected {len(final_selected_tracks)} tracks for the final time window playlist ({'sonically sorted' if config.TIME_PLAYLIST_SONIC_SORT and len(final_selected_tracks) > 1 else 'randomly selected/shuffled'}).")
        return final_selected_tracks
    
    def generate_harmoniq_flow_playlist(self,
                                    libraries: list[LibrarySection],
                                    active_period_name: str,
                                    # target_moods and target_styles will be determined *after* vibe learning
                                    base_target_moods: list[str], # From config (default or user override)
                                    base_target_styles: list[str],# From config (default or user override)
                                    period_active_hours: set[int],
                                    playlist_target_size: int
                                    ) -> list[PlexApiTrack]:
        logger.info(f"--- Generating Harmoniq Flow for Period: {active_period_name} ---")
        actual_limit = playlist_target_size if playlist_target_size > 0 else 40
        if playlist_target_size <= 0: logger.warning(f"Target size ({playlist_target_size}) not positive. Defaulting to 40.")
        logger.info(f"Targeting {actual_limit} tracks. Base Vibe - Moods: {base_target_moods}, Styles/Genres: {base_target_styles}")

        logger.info(f"Targeting {playlist_target_size} tracks.")
        # Log other relevant settings
        logger.info(f"History Integration: {config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS}, Target History Count: {config.TIME_PLAYLIST_TARGET_HISTORY_COUNT}")
        logger.info(f"Sonic Adventure Bridging: {config.TIME_PLAYLIST_USE_SONIC_ADVENTURE}")
        logger.info(f"Sonic Expansion Feature: {config.TIME_PLAYLIST_USE_SONIC_EXPANSION}")
        logger.info(f"Sonic Sort Feature: {config.TIME_PLAYLIST_SONIC_SORT}")


        history_lookback = config.TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS # For selecting familiar anchors
        
        # This call fetches tracks played *during period_active_hours* within *history_lookback* days
        all_period_historical_tracks = []
        if config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS or config.TIME_PLAYLIST_LEARN_FROM_HISTORY:
             all_period_historical_tracks = self._get_raw_historical_tracks_for_period_hours(
                 libraries, 
                 history_lookback, # Use the lookback intended for finding "familiar" tracks
                 period_active_hours
             )

        # --- Vibe Learning/Augmentation Step ---
        effective_moods = list(base_target_moods) # Start with base/override
        effective_styles = list(base_target_styles)

        if config.TIME_PLAYLIST_LEARN_FROM_HISTORY:
            logger.info(f"Attempting to learn dominant vibes from {len(all_period_historical_tracks)} tracks from history for period '{active_period_name}'...")
            # Pass the already fetched historical tracks for this period to the analysis function
            dominant_hist_moods, dominant_hist_styles_genres = self._analyze_historical_vibe_for_period(
                # libraries, period_active_hours, # No longer passes these
                all_period_historical_tracks # Pass the pre-fetched list
            )
            if dominant_hist_moods:
                logger.info(f"Augmenting target moods with learned: {dominant_hist_moods}")
                for mood in dominant_hist_moods:
                    if mood not in effective_moods: effective_moods.append(mood)
            if dominant_hist_styles_genres:
                logger.info(f"Augmenting target styles/genres with learned: {dominant_hist_styles_genres}")
                for sg in dominant_hist_styles_genres:
                    if sg not in effective_styles: effective_styles.append(sg)
        
        logger.info(f"Effective Vibe for '{active_period_name}' - Moods: {effective_moods}, Styles/Genres: {effective_styles}")

        # Now use effective_moods and effective_styles for anchor selection

        # 1. Select Vibe Anchors (Discovery - uses effective vibe)
        num_vibe_anchors_to_select = config.TIME_PLAYLIST_VIBE_ANCHOR_COUNT
        vibe_anchors = self._select_vibe_anchors(libraries, effective_moods, effective_styles, num_vibe_anchors_to_select)
        logger.info(f"Selected {len(vibe_anchors)} Vibe Anchors: {[t.title for t in vibe_anchors]}")

        # 2. Select Familiar Anchors (History - uses effective vibe for compatibility check)
        familiar_anchors = []
        num_familiar_anchors_to_select = config.TIME_PLAYLIST_TARGET_HISTORY_COUNT
        if config.TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS:
            # Pass the pre-fetched all_period_historical_tracks
            familiar_anchors = self._select_familiar_anchors(
                # libraries, # No longer needed here
                effective_moods, # Check compatibility against the (augmented) effective vibe
                effective_styles, 
                num_familiar_anchors_to_select, 
                # period_active_hours, # No longer needed here
                all_period_historical_tracks # Pass the pre-fetched list
            )
            logger.info(f"Selected {len(familiar_anchors)} Familiar Anchors: {[t.title for t in familiar_anchors]}")

        # --- Build Skeleton Playlist ---
        skeleton_playlist: list[PlexApiTrack] = []; temp_vibe_anchors = list(vibe_anchors); temp_familiar_anchors = list(familiar_anchors); skeleton_keys = set()
        while temp_vibe_anchors or temp_familiar_anchors:
            if temp_familiar_anchors: anchor = temp_familiar_anchors.pop(0);_ = (skeleton_playlist.append(anchor), skeleton_keys.add(anchor.ratingKey)) if anchor.ratingKey not in skeleton_keys else None
            if temp_vibe_anchors: anchor = temp_vibe_anchors.pop(0); _ = (skeleton_playlist.append(anchor), skeleton_keys.add(anchor.ratingKey)) if anchor.ratingKey not in skeleton_keys else None
        if not skeleton_playlist and (vibe_anchors or familiar_anchors): # Fallback
            skeleton_playlist.extend(vibe_anchors); skeleton_keys.update(t.ratingKey for t in vibe_anchors)
            for fa_fb in familiar_anchors:
                if fa_fb.ratingKey not in skeleton_keys: skeleton_playlist.append(fa_fb); skeleton_keys.add(fa_fb.ratingKey)
        logger.info(f"Built skeleton playlist with {len(skeleton_playlist)} unique anchors: {[t.title for t in skeleton_playlist]}")

        # --- Bridge Anchors with Sonic Adventure OR use Greedy Sort ---
        final_playlist_tracks: list[PlexApiTrack] = []
        processed_final_keys = set() 

        if config.TIME_PLAYLIST_USE_SONIC_ADVENTURE and len(skeleton_playlist) >= 2:
            logger.info("Bridging skeleton anchors with Sonic Adventure...")
            for i in range(len(skeleton_playlist)): 
                current_anchor = skeleton_playlist[i]
                if current_anchor.ratingKey not in processed_final_keys:
                    final_playlist_tracks.append(current_anchor)
                    processed_final_keys.add(current_anchor.ratingKey)
                if i < len(skeleton_playlist) - 1:
                    next_anchor = skeleton_playlist[i+1]
                    logger.debug(f"Attempting Sonic Adventure between '{current_anchor.title}' AND '{next_anchor.title}'")
                    adventure_path = []
                    try:
                        start_anchor_lib_obj = current_anchor.section()
                        if start_anchor_lib_obj and start_anchor_lib_obj.type == 'artist':
                            logger.debug(f"Using library '{start_anchor_lib_obj.title}' for Sonic Adventure.")
                            time.sleep(0.2) 
                            adventure_path = start_anchor_lib_obj.sonicAdventure(start=current_anchor, end=next_anchor)
                            logger.debug(f"Sonic Adventure found {len(adventure_path)} tracks for path.")
                        elif not start_anchor_lib_obj: logger.warning(f"Could not get library section for '{current_anchor.title}' for sonicAdventure.")
                        elif start_anchor_lib_obj.type != 'artist': logger.warning(f"Library section for '{current_anchor.title}' not music library. Skipping sonicAdventure.")
                    except PlexApiException as e: logger.warning(f"Sonic Adventure failed between '{current_anchor.title}' and '{next_anchor.title}': {e}")
                    except Exception as e: logger.exception(f"Unexpected error during Sonic Adventure: {e}")
                    if adventure_path:
                        filtered_adventure_tracks = self._apply_common_filters(adventure_path, is_historical_track_list=False)
                        logger.debug(f"{len(filtered_adventure_tracks)} adventure tracks remain after filtering.")
                        for adv_track in filtered_adventure_tracks:
                            if adv_track.ratingKey not in processed_final_keys:
                                final_playlist_tracks.append(adv_track); processed_final_keys.add(adv_track.ratingKey)
            logger.info(f"Playlist size after Sonic Adventures: {len(final_playlist_tracks)}")
        else: 
            logger.info("Sonic Adventure not used or not enough anchors. Using combined anchors directly.")
            for sk_track in skeleton_playlist: 
                if sk_track.ratingKey not in processed_final_keys:
                    final_playlist_tracks.append(sk_track); processed_final_keys.add(sk_track.ratingKey)
            if config.TIME_PLAYLIST_SONIC_SORT and len(final_playlist_tracks) > 1:
                logger.info("Applying Greedy Sonic Sort to anchor list as Sonic Adventure was not run.")
                final_playlist_tracks = self._sort_by_sonic_similarity_greedy(
                    final_playlist_tracks,
                    score_limit=config.TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT,
                    score_max_distance=config.TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE)
        
        # --- Optional Sonic Expansion ---
        MAX_TRACKS_PER_ARTIST_FOR_EXPANSION_FILL = 2
        if config.TIME_PLAYLIST_USE_SONIC_EXPANSION and len(final_playlist_tracks) < actual_limit:
            logger.info("Attempting Sonic Expansion to fill remaining playlist space...")
            num_needed_for_expansion = actual_limit - len(final_playlist_tracks)
            num_expansion_seeds = min(config.TIME_PLAYLIST_SONIC_SEED_TRACKS, len(final_playlist_tracks))
            if num_expansion_seeds > 0 and num_needed_for_expansion > 0:
                expansion_seed_tracks = random.sample(final_playlist_tracks, k=num_expansion_seeds)
                logger.debug(f"Selected {len(expansion_seed_tracks)} seeds for post-adventure sonic expansion.")
                temp_expansion_candidates = []
                for i, seed_track in enumerate(expansion_seed_tracks):
                    logger.debug(f"Fetching expansion tracks for seed {i+1}/{num_expansion_seeds}: '{seed_track.title}'") # num_expansion_seeds is correct here
                    try:
                        time.sleep(0.1)
                        fetch_per_seed = max(3, (num_needed_for_expansion // num_expansion_seeds) + 2 if num_expansion_seeds > 0 else 3)
                        similar = seed_track.sonicallySimilar(limit=min(fetch_per_seed, config.TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED * 2), maxDistance=config.TIME_PLAYLIST_SONIC_MAX_DISTANCE)
                        for s_track in similar: # No processed_final_keys check here, collect all, filter later
                            temp_expansion_candidates.append(s_track)
                    except PlexApiException as e: logger.warning(f"Sonic expansion error for '{seed_track.title}': {e}")
                    except Exception as e: logger.exception(f"Unexpected error during sonic expansion for '{seed_track.title}': {e}")
                if temp_expansion_candidates:
                    logger.info(f"Collected {len(temp_expansion_candidates)} unique tracks from sonic expansion (before filtering).")
                    unique_temp_expansion_candidates = list({t.ratingKey: t for t in temp_expansion_candidates}.values())
                    filtered_expansion_tracks = self._apply_common_filters(unique_temp_expansion_candidates, is_historical_track_list=False)
                    logger.info(f"{len(filtered_expansion_tracks)} expansion tracks remaining after filters.")
                    
                    artist_counts_expansion_fill = {}
                    added_expansion_count = 0
                    random.shuffle(filtered_expansion_tracks)
                    for exp_track in filtered_expansion_tracks:
                        if len(final_playlist_tracks) >= actual_limit: break
                        if exp_track.ratingKey not in processed_final_keys:
                            artist_title = exp_track.grandparentTitle
                            if artist_counts_expansion_fill.get(artist_title, 0) < MAX_TRACKS_PER_ARTIST_FOR_EXPANSION_FILL:
                                final_playlist_tracks.append(exp_track)
                                processed_final_keys.add(exp_track.ratingKey)
                                artist_counts_expansion_fill[artist_title] = artist_counts_expansion_fill.get(artist_title, 0) + 1
                                added_expansion_count +=1
                            else:
                                logger.debug(f"Skipping expansion track '{exp_track.title}' by '{artist_title}', artist limit reached for this fill stage.")
                    logger.info(f"Added {added_expansion_count} tracks from sonic expansion. Playlist size: {len(final_playlist_tracks)}")

        # --- Padding with more mood/genre tracks if still short ---
        MAX_TRACKS_PER_ARTIST_FOR_PADDING_FILL = 2
        if len(final_playlist_tracks) < actual_limit:
            needed = actual_limit - len(final_playlist_tracks)
            logger.info(f"Playlist still short by {needed}. Fetching more mood/genre discovery tracks for padding...")
            additional_discovery = []
            fetch_limit_padding = needed * 10
            for lib in libraries:
                tracks = self._get_tracks_matching_mood_genre_style(lib, target_moods, target_styles, fetch_limit_padding)
                for track in tracks:
                    additional_discovery.append(track)
            if additional_discovery:
                unique_additional_discovery = list({t.ratingKey: t for t in additional_discovery if t.ratingKey not in processed_final_keys}.values())
                filtered_additional_discovery = self._apply_common_filters(unique_additional_discovery, is_historical_track_list=False)
                logger.info(f"Found {len(filtered_additional_discovery)} additional discovery tracks for padding (after filters & initial dedupe).")
                
                artist_counts_padding_fill = {}
                added_padding_count = 0
                random.shuffle(filtered_additional_discovery)
                for pad_track in filtered_additional_discovery:
                    if len(final_playlist_tracks) >= actual_limit: break
                    if pad_track.ratingKey not in processed_final_keys:
                        artist_title = pad_track.grandparentTitle
                        if artist_counts_padding_fill.get(artist_title, 0) < MAX_TRACKS_PER_ARTIST_FOR_PADDING_FILL:
                            final_playlist_tracks.append(pad_track)
                            processed_final_keys.add(pad_track.ratingKey)
                            artist_counts_padding_fill[artist_title] = artist_counts_padding_fill.get(artist_title, 0) + 1
                            added_padding_count +=1
                        else:
                            logger.debug(f"Skipping padding track '{pad_track.title}' by '{artist_title}', artist limit reached for this fill stage.")
                logger.info(f"Added {added_padding_count} padding tracks. Playlist size: {len(final_playlist_tracks)}")

        # --- Final Deduplication, Sort, and Limit ---
        unique_final_tracks = list(dict.fromkeys(final_playlist_tracks))
        if not config.TIME_PLAYLIST_USE_SONIC_ADVENTURE and config.TIME_PLAYLIST_SONIC_SORT and len(unique_final_tracks) > 1:
            logger.info("Applying Greedy Sonic Sort as a final step (Sonic Adventure was not used).")
            selected_tracks = self._sort_by_sonic_similarity_greedy(unique_final_tracks, config.TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT, config.TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE)
        else:
            if not config.TIME_PLAYLIST_USE_SONIC_ADVENTURE and not config.TIME_PLAYLIST_SONIC_SORT: random.shuffle(unique_final_tracks)
            selected_tracks = unique_final_tracks
        
        final_k = min(actual_limit, len(selected_tracks))
        final_selected_tracks = selected_tracks[:final_k]
        
        flow_method = "unknown"
        if config.TIME_PLAYLIST_USE_SONIC_ADVENTURE and len(skeleton_playlist) >=2 and any(adv_track for adv_track in final_selected_tracks if adv_track.ratingKey not in skeleton_keys) : flow_method = "sonic adventure paths" # Check if adventure actually added tracks
        elif config.TIME_PLAYLIST_SONIC_SORT and len(final_selected_tracks) > 1: flow_method = "greedy sonic sort"
        else: flow_method = "mood/genre + expansion (randomized)"
        logger.info(f"Selected {len(final_selected_tracks)} tracks for '{active_period_name}' Harmoniq Flow (flow by: {flow_method}).")
        return final_selected_tracks
    
    def _analyze_historical_vibe_for_period(self, 
                                        # libraries: list[LibrarySection], # No longer needs libraries
                                        # period_active_hours: set[int], # No longer needs hours
                                        # lookback_days: int, # No longer needs lookback
                                        historical_tracks_for_period: list[PlexApiTrack] # Receives pre-fetched tracks
                                        ) -> tuple[list[str], list[str]]:
        if not config.TIME_PLAYLIST_LEARN_FROM_HISTORY:
            logger.debug("Vibe learning from history is disabled in config.")
            return [], []
        
        # `historical_tracks_for_period` are already filtered by hour and lookback by the caller

        if not historical_tracks_for_period:
            logger.info("No historical tracks provided for vibe learning analysis.")
            return [], []
        
        logger.info(f"Analyzing {len(historical_tracks_for_period)} provided historical tracks for dominant vibes.")

        mood_counts = Counter()
        style_genre_counts = Counter() 
        for track in historical_tracks_for_period:
            if hasattr(track, 'moods') and track.moods:
                for mood_tag in track.moods:
                    if mood_tag and mood_tag.tag: mood_counts[mood_tag.tag.capitalize()] += 1
            if hasattr(track, 'genres') and track.genres:
                for genre_tag in track.genres:
                    if genre_tag and genre_tag.tag: style_genre_counts[genre_tag.tag.capitalize()] += 1
        
        min_occurrences = config.TIME_PLAYLIST_LEARNED_VIBE_MIN_OCCURRENCES
        dominant_moods = [m for m,c in mood_counts.most_common(config.TIME_PLAYLIST_LEARNED_VIBE_TOP_N_MOODS) if c >= min_occurrences]
        dominant_styles_genres = [sg for sg,c in style_genre_counts.most_common(config.TIME_PLAYLIST_LEARNED_VIBE_TOP_M_STYLES) if c >= min_occurrences]

        logger.info(f"Dominant historical moods from provided tracks: {dominant_moods}")
        logger.info(f"Dominant historical styles/genres from provided tracks: {dominant_styles_genres}")
        return dominant_moods, dominant_styles_genres
    
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
    
    def upload_playlist_cover(self, playlist_obj: Playlist, image_filepath: str):
        """Uploads a cover image to the specified Plex playlist object."""
        if not playlist_obj:
            logger.error("Cannot upload cover: Invalid playlist object provided.")
            return False
        if not image_filepath or not os.path.exists(image_filepath):
            logger.error(f"Cannot upload cover: Image file not found at '{image_filepath}'.")
            return False
        
        try:
            logger.info(f"Uploading cover '{image_filepath}' to playlist '{playlist_obj.title}'...")
            playlist_obj.uploadPoster(filepath=image_filepath)
            logger.info("Playlist cover uploaded successfully.")
            return True
        except Exception as e:
            logger.exception(f"Failed to upload cover to playlist '{playlist_obj.title}': {e}")
            return False