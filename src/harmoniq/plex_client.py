# src/harmoniq/plex_client.py
import logging
import time # Import time for potential delays/retries if needed later
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized, BadRequest
from plexapi.playlist import Playlist # Import Playlist type hint

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

    def get_music_library(self, library_name=config.PLEX_MUSIC_LIBRARY_NAMES):
        """Gets the specified music library object from the Plex server."""
        if not self.plex:
            logger.error("Cannot get library: Not connected to Plex.")
            return None
        try:
            logger.info(f"Accessing music library: '{library_name}'")
            music_library = self.plex.library.section(library_name)
            if music_library.type != 'artist':
                 logger.error(f"Section '{library_name}' is not a Music library (type: {music_library.type}).")
                 return None
            logger.info(f"Successfully accessed library '{music_library.title}'.")
            return music_library
        except NotFound:
            logger.error(f"Music library '{library_name}' not found on the Plex server.")
            return None
        except Exception as e:
            logger.error(f"An error occurred accessing library '{library_name}': {e}")
            return None

    # --- IMPLEMENTED METHODS ---
    def find_track(self, music_library, artist_name, track_title):
        """
        Searches for a specific track within a given music library.
        Returns the Plex Track object if found, otherwise None.
        """
        if not music_library:
            logger.error("Cannot search track: Music library object is invalid.")
            return None
        if not artist_name or not track_title:
            logger.warning("Cannot search track: Artist name or track title is missing.")
            return None

        try:
            # --- CORRECTED SEARCH ---
            # Filter by track title and the track's grandparent (artist) title
            # Using 'title__iexact' and 'grandparentTitle__iexact' might offer case-insensitive exact matching
            # Alternatively, 'title__icontains' and 'grandparentTitle__icontains' for broader matching
            # Let's start with case-insensitive exact matching as it's less likely to give wrong results.
            search_filters = {
                'title__iexact': track_title,
                'grandparentTitle__iexact': artist_name
            }
            logger.debug(f"Searching for track with filters: {search_filters} in library '{music_library.title}'")

            # Use the 'search' method with filters directly for more control
            # results = music_library.searchTracks(title=track_title, artist=artist_name) <-- Incorrect way
            results = music_library.search(libtype='track', filters=search_filters) # <-- Corrected way

            if not results:
                # Try a slightly broader search (case-insensitive contains) as a fallback? Optional.
                logger.debug(f"Track not found with exact match. Trying broader search for '{artist_name} - {track_title}'...")
                search_filters_broad = {
                    'title__icontains': track_title,
                    'grandparentTitle__icontains': artist_name
                }
                results = music_library.search(libtype='track', filters=search_filters_broad)
                if not results:
                     logger.debug(f"Track still not found with broader search: {artist_name} - {track_title}")
                     return None # Definitely not found

            # Handle multiple results. For now, take the first one.
            if len(results) > 1:
                found_details = [f"'{t.title}' by '{t.grandparentTitle}' (Album: '{t.parentTitle}')" for t in results[:3]]
                logger.debug(f"Multiple ({len(results)}) matches found for '{artist_name} - {track_title}'. Using first: {found_details[0]}. Other matches: {found_details[1:]}")

            track = results[0]
            logger.debug(f"Found matching track: '{track.title}' by '{track.grandparentTitle}' (Key: {track.key})")
            return track

        except BadRequest as e:
             # This might happen if filter fields are still wrong
             logger.error(f"BadRequest searching Plex for '{artist_name} - {track_title}': {e}. Check filter fields.")
             return None
        except Exception as e:
            logger.error(f"Unexpected error searching Plex for '{artist_name} - {track_title}': {e}")
            return None

    def update_playlist(self, playlist_name: str, tracks_to_add: list, music_library):
        """
        Creates a new Plex playlist or updates an existing one by clearing
        and adding the provided tracks.

        Args:
            playlist_name: Name of the playlist to create/update.
            tracks_to_add: A list of plexapi.audio.Track objects.
            music_library: The plexapi.library.LibrarySection object (used for context if creating).
        """
        if not self.plex:
            logger.error("Cannot update playlist: Not connected to Plex.")
            return False
        if not playlist_name:
            logger.error("Cannot update playlist: Playlist name is empty.")
            return False
        if not music_library: # Needed for context when creating playlist
             logger.error("Cannot update playlist: Music library context is missing.")
             return False
        if not tracks_to_add:
             logger.info(f"No tracks provided to add to playlist '{playlist_name}'. Skipping update.")
             # Optionally delete playlist if empty? For now, just do nothing.
             return True # Technically successful, as there was nothing to do

        try:
            playlist: Playlist = None
            # Check if playlist exists
            try:
                logger.debug(f"Checking for existing playlist: '{playlist_name}'")
                playlist = self.plex.playlist(playlist_name)
                logger.info(f"Found existing playlist '{playlist_name}'. Clearing items...")
                # Clear existing items
                playlist.removeItems(playlist.items()) # Pass the actual items to remove
                # Small delay might help prevent race conditions? (optional)
                # time.sleep(1)

            except NotFound:
                logger.info(f"Playlist '{playlist_name}' not found. Creating new playlist...")
                # Create playlist - requires items and a library context (use first track's library?)
                # Using the passed music_library section seems more robust.
                playlist = self.plex.createPlaylist(playlist_name, section=music_library, items=tracks_to_add)
                logger.info(f"Successfully created playlist '{playlist_name}' with {len(tracks_to_add)} tracks.")
                # No need to add items again if created with items
                return True

            # If playlist existed and was cleared, add the new items
            if playlist:
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

        except BadRequest as e:
             # Catch specific errors like trying to add items from different libraries
             logger.error(f"BadRequest error updating playlist '{playlist_name}': {e}. Ensure all tracks are from the same library.")
             return False
        except Exception as e:
             logger.error(f"An unexpected error occurred updating playlist '{playlist_name}': {e}")
             return False

        return False # Should not be reached, but default to failure