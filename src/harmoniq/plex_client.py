# src/harmoniq/plex_client.py
import logging
import time
import random # For sampling tracks
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized, BadRequest
from plexapi.playlist import Playlist
from plexapi.library import LibrarySection # Import LibrarySection type hint

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

    # --- NEW METHOD FOR TIME-BASED PLAYLISTS ---
    def find_tracks_by_criteria(self,
                                libraries: list[LibrarySection],
                                moods: list[str] = None,
                                styles: list[str] = None, # We'll treat styles as genres
                                limit: int = 50,
                                exclude_played_days: int | None = None): # Placeholder for future use
        """
        Finds tracks across specified libraries matching ANY of the given moods
        AND ANY of the given styles (treated as genres).

        Args:
            libraries: List of Plex LibrarySection objects to search.
            moods: List of mood strings to match (case-insensitive).
            styles: List of style/genre strings to match (case-insensitive).
            limit: Maximum number of tracks to return.
            exclude_played_days: (Optional) Exclude tracks played in the last X days (Not yet implemented).
        """
        if not libraries:
            logger.error("Cannot find tracks by criteria: No libraries provided.")
            return []

        # Prepare lists, ensuring they are lowercase for case-insensitive matching if Plex filters are exact
        # However, for direct filter values with Plex, original casing might be needed or __iexact used.
        # Let's assume Plex Sonic Analysis tags (Moods, Styles/Genres) are stored with specific casing.
        # The filter should handle case-insensitivity via __icontains or __iexact if supported.
        # For now, we'll pass them as capitalized from config and see how Plex handles it.
        
        # Convert to lowercase for logging and potential Python-side filtering if needed
        log_moods = [m.lower() for m in moods if m] if moods else []
        log_genres = [s.lower() for s in styles if s] if styles else [] # Treat styles as genres

        logger.info(f"Searching for tracks with Moods: {moods if moods else 'Any'} AND Genres: {styles if styles else 'Any'}")

        candidate_tracks = []
        all_fetched_rating_keys = set() # To avoid processing exact same track twice if found via different criteria paths

        for library in libraries:
            logger.debug(f"Searching for criteria-based tracks in library: '{library.title}'")
            
            plex_filters = {}
            # IMPORTANT: Plex filter syntax for multiple values for one key (e.g. track.mood) is OR.
            # If multiple keys are provided (e.g. track.mood and track.genre), it's an AND between them.
            # track.mood = ['Happy', 'Energetic'] -> mood is Happy OR Energetic
            # track.genre = ['Rock', 'Pop'] -> genre is Rock OR Pop
            # Both filters applied: (mood is Happy OR Energetic) AND (genre is Rock OR Pop)

            if moods:
                # Filter key `track.mood` expects the mood tag exactly as Plex stores it.
                plex_filters['track.mood'] = moods # Pass the list of mood strings
            if styles: # Treat styles as genres
                plex_filters['track.genre'] = styles # Pass the list of style/genre strings

            if not plex_filters:
                logger.info(f"No mood or style/genre criteria specified for library '{library.title}'. Skipping library for this criteria search.")
                continue

            try:
                logger.debug(f"Attempting Plex search in '{library.title}' with filters: {plex_filters}")
                # Fetch a larger pool to sample from, Plex applies its own internal limit first.
                # We want to give Plex as much info as possible to do the heavy lifting.
                MAX_FETCH_PER_LIB_CRITERIA = limit * 5 # Arbitrary multiplier
                
                # library.search() is preferred over library.all() when filters are known
                tracks_from_plex = library.search(libtype='track', limit=MAX_FETCH_PER_LIB_CRITERIA, filters=plex_filters)
                
                logger.debug(f"Found {len(tracks_from_plex)} tracks initially matching criteria in '{library.title}'.")
                for track in tracks_from_plex:
                    if track.ratingKey not in all_fetched_rating_keys:
                        candidate_tracks.append(track)
                        all_fetched_rating_keys.add(track.ratingKey)

            except BadRequest as e:
                 logger.error(f"BadRequest searching by criteria in '{library.title}': {e}. Filter keys for mood/genre might be incorrect or not supported as expected.")
            except Exception as e:
                 logger.exception(f"Unexpected error searching by criteria in '{library.title}': {e}")
        
        logger.info(f"Found {len(candidate_tracks)} total unique candidate tracks matching criteria across all libraries.")

        if not candidate_tracks:
            return []

        # --- Further Python-based filtering (e.g., exclude_played_days) ---
        # Placeholder for now
        # if exclude_played_days is not None:
        #     # (Logic to filter by lastViewedAt) ...
        #     logger.info(f"{len(candidate_tracks)} tracks remaining after play history filter.")

        # Shuffle and limit
        # Use random.sample to get a unique list of k items.
        # Ensure k is not greater than the population size.
        k = min(limit, len(candidate_tracks))
        selected_tracks = random.sample(candidate_tracks, k=k)
        
        logger.info(f"Selected {len(selected_tracks)} tracks for time window playlist.")
        return selected_tracks