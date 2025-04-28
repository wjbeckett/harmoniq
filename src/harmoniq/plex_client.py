# src/harmoniq/plex_client.py
import logging
import time
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized, BadRequest
from plexapi.playlist import Playlist
from plexapi.library import LibrarySection # Import LibrarySection type hint

# Import config variables (still needed for defaults if main doesn't pass them)
from . import config

logger = logging.getLogger(__name__)

class PlexClient:
    """Handles interactions with the Plex Media Server."""

    # __init__ and _connect remain the same

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
            logger.error("Plex connection failed: Invalid Plex Token.")
            self.plex = None
            raise
        except NotFound:
            logger.error(f"Plex connection failed: Server not found at {self.baseurl}. Check URL.")
            self.plex = None
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred connecting to Plex: {e}")
            self.plex = None
            raise

    def get_music_library(self, library_name: str) -> LibrarySection | None:
        """
        Gets a specific music library object by name from the Plex server.

        Args:
            library_name: The exact name of the music library section.

        Returns:
            A plexapi LibrarySection object if found and is a music library, otherwise None.
        """
        if not self.plex:
            logger.error("Cannot get library: Not connected to Plex.")
            return None
        if not library_name:
            logger.error("Cannot get library: No library name provided.")
            return None

        try:
            logger.debug(f"Attempting to access music library: '{library_name}'")
            music_library = self.plex.library.section(library_name)
            # Validate type
            if music_library.type != 'artist':
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
        if not music_libraries:
            logger.error("Cannot search track: List of music libraries is empty or invalid.")
            return None
        if not artist_name or not track_title:
            logger.warning("Cannot search track: Artist name or track title is missing.")
            return None

        search_term_log = f"'{artist_name} - {track_title}'"
        logger.debug(f"Searching for track {search_term_log} across {len(music_libraries)} libraries...")

        for library in music_libraries:
            logger.debug(f"Searching in library: '{library.title}'")
            results = []
            try:
                # --- CORRECTED SEARCH - Attempt 4: Using filters dict again ---
                # Try using 'artist.title' as the filter field name for the artist.

                # Try case-insensitive exact match first
                logger.debug(f"Attempting exact search with filters: title__iexact='{track_title}', artist.title__iexact='{artist_name}'")
                search_filters_exact = {
                    'title__iexact': track_title,
                    'artist.title__iexact': artist_name # Using dot notation for related field
                }
                results = library.search(libtype='track', filters=search_filters_exact)

                if not results:
                    # Fallback: Try broader contains match (case-insensitive)
                    logger.debug(f"Track not found with exact filter match. Trying broader contains search...")
                    search_filters_broad = {
                        'title__icontains': track_title,
                        'artist.title__icontains': artist_name # Using dot notation for related field
                    }
                    results = library.search(libtype='track', filters=search_filters_broad)

                    if not results:
                         logger.debug(f"Track still not found with broader filter search in '{library.title}'.")
                         continue # Move to the next library

                # Found results in this library
                if len(results) > 1:
                    found_details = [f"'{t.title}' by '{t.grandparentTitle}' (Album: '{t.parentTitle}')" for t in results[:3]]
                    logger.debug(f"Multiple ({len(results)}) matches found for {search_term_log} in '{library.title}'. Using first: {found_details[0]}. Other matches: {found_details[1:]}")
                track = results[0]
                # Use INFO level for successful finds for better visibility
                logger.info(f"Found matching track in '{library.title}': '{track.title}' by '{track.grandparentTitle}' (Key: {track.key})")
                return track # Return the first match found

            except BadRequest as e:
                 # This indicates the filter field name itself ('artist.title__iexact' etc.) is wrong
                 logger.error(f"BadRequest searching Plex in library '{library.title}' for {search_term_log}: {e}. Filter field 'artist.title' likely incorrect.")
                 # Since the filter is wrong, no point searching other libraries with it. Break? Or just log and continue? Let's continue for now.
            except Exception as e:
                 logger.exception(f"Unexpected error searching Plex in library '{library.title}' for {search_term_log}: {e}")
                 # Continue searching in the next library

        # If loop finishes without finding the track
        logger.info(f"Track {search_term_log} not found in any library after all searches.")
        return None

    # update_playlist remains the same - it takes a specific library context for creation
    def update_playlist(self, playlist_name: str, tracks_to_add: list, music_library: LibrarySection):
        """
        Creates a new Plex playlist or updates an existing one by clearing
        and adding the provided tracks.

        Args:
            playlist_name: Name of the playlist to create/update.
            tracks_to_add: A list of plexapi.audio.Track objects.
            music_library: The plexapi.library.LibrarySection object to use for context if creating the playlist.
        """
        if not self.plex:
            logger.error("Cannot update playlist: Not connected to Plex.")
            return False
        if not playlist_name:
            logger.error("Cannot update playlist: Playlist name is empty.")
            return False
        if not music_library: # Still needed for context when creating a new playlist
             logger.error("Cannot update playlist: Target music library context is missing for potential creation.")
             return False
        # Check if tracks_to_add is empty is already handled

        try:
            playlist: Playlist = None
            # Check if playlist exists (Playlists are server-wide, not library specific in plexapi lookup)
            try:
                logger.debug(f"Checking for existing playlist: '{playlist_name}'")
                playlist = self.plex.playlist(playlist_name) # This finds the playlist by name globally
                logger.info(f"Found existing playlist '{playlist_name}'. Clearing items...")
                # Clear existing items
                if playlist.items(): # Check if there are items before trying to remove
                     playlist.removeItems(playlist.items())
                else:
                     logger.debug("Existing playlist is empty, no items to clear.")
                # time.sleep(1) # Optional delay

            except NotFound:
                logger.info(f"Playlist '{playlist_name}' not found. Creating new playlist...")
                # Create playlist - requires items and a library context
                if not tracks_to_add:
                     logger.info(f"No tracks to add, skipping creation of empty playlist '{playlist_name}'.")
                     return True # Or False depending on desired behaviour for empty creation
                playlist = self.plex.createPlaylist(playlist_name, section=music_library, items=tracks_to_add)
                logger.info(f"Successfully created playlist '{playlist_name}' in context of library '{music_library.title}' with {len(tracks_to_add)} tracks.")
                return True

            # If playlist existed and was cleared, add the new items (if any)
            if playlist and tracks_to_add:
                 logger.info(f"Adding {len(tracks_to_add)} tracks to playlist '{playlist_name}'...")
                 playlist.addItems(tracks_to_add)
                 logger.info(f"Successfully updated playlist '{playlist_name}' with {len(tracks_to_add)} tracks.")

                 # Optional: Update summary
                 try:
                     now = time.strftime("%Y-%m-%d %H:%M:%S %Z")
                     playlist.editSummary(f"Updated by Harmoniq on {now}. Contains {len(tracks_to_add)} tracks.")
                 except Exception as e:
                     logger.warning(f"Could not update summary for playlist '{playlist_name}': {e}")

                 return True
            elif playlist and not tracks_to_add:
                logger.info(f"Playlist '{playlist_name}' exists but has no new tracks to add.")
                # Optionally update summary to reflect it's empty now?
                return True # Successful update (to empty state)


        except BadRequest as e:
             # Catch specific errors like trying to add items from different libraries
             logger.error(f"BadRequest error updating playlist '{playlist_name}': {e}. This might indicate tracks are from different libraries or other issues.")
             return False
        except Exception as e:
             logger.exception(f"An unexpected error occurred updating playlist '{playlist_name}': {e}") # Use exception for full trace
             return False

        # Fallback case - should ideally not be reached
        logger.error(f"Reached end of update_playlist for '{playlist_name}' without clear success/failure.")
        return False