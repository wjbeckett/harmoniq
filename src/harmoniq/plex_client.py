# src/harmoniq/plex_client.py
import logging
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized

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
            # Raising here prevents instantiation with bad config
            raise ValueError("Plex URL or Token is missing.")
        try:
            logger.info(f"Connecting to Plex server at {self.baseurl}...")
            # Increased timeout might be helpful on slower networks or servers
            self.plex = PlexServer(self.baseurl, self.token, timeout=30)
            # Test connection by getting server identity (optional but good check)
            server_name = self.plex.friendlyName
            logger.info(f"Successfully connected to Plex server: {server_name}")
        except Unauthorized:
            logger.error("Plex connection failed: Invalid Plex Token.")
            self.plex = None
            raise # Re-raise after logging
        except NotFound:
            logger.error(f"Plex connection failed: Server not found at {self.baseurl}. Check URL.")
            self.plex = None
            raise # Re-raise after logging
        except Exception as e:
            logger.error(f"An unexpected error occurred connecting to Plex: {e}")
            self.plex = None
            raise # Re-raise after logging

    def get_music_library(self, library_name=config.PLEX_MUSIC_LIBRARY_NAME):
        """Gets the specified music library object from the Plex server."""
        if not self.plex:
            logger.error("Cannot get library: Not connected to Plex.")
            return None
        try:
            logger.info(f"Accessing music library: '{library_name}'")
            music_library = self.plex.library.section(library_name)
            if music_library.type != 'artist': # Check if it's actually a music library
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

    # --- Placeholder for future methods ---
    def find_track(self, music_library, artist_name, track_title):
        """Searches for a specific track within a given music library."""
        # To be implemented later in Phase 1
        logger.warning(f"Placeholder: find_track('{artist_name}', '{track_title}') not implemented.")
        return None

    def update_playlist(self, playlist_name, tracks_to_add, music_library):
        """Creates or updates a Plex playlist with the given tracks."""
        # To be implemented later in Phase 1
        logger.warning(f"Placeholder: update_playlist('{playlist_name}') not implemented.")
        return None