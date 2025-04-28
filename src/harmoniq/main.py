# src/harmoniq/main.py
import logging
# Import config variables
from . import config
# Import logger configured in log_config
from .log_config import logger
# Import Clients
from .plex_client import PlexClient
from .lastfm_client import LastfmClient

def run_playlist_update_cycle():
    """
    Main logic loop that connects to services, fetches data,
    matches tracks, and updates Plex playlists.
    """
    logger.info("Starting playlist update cycle...")

    plex_client = None
    lastfm_client = None

    # --- Connect to Services ---
    try:
        plex_client = PlexClient() # Connection happens in __init__
        # Instantiate Last.fm client (it handles missing keys internally)
        lastfm_client = LastfmClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}. Aborting update cycle.")
        return # Stop cycle if essential clients fail

    # --- Get Plex Library ---
    music_library = None
    if plex_client:
        music_library = plex_client.get_music_library()
        if not music_library:
            logger.error("Could not access Plex music library. Aborting update cycle.")
            return # Stop if library not found/accessible

    # --- Process Enabled Playlist Types ---

    # 1. Last.fm Recommendations
    if config.ENABLE_LASTFM_RECS and lastfm_client and lastfm_client.api_key and music_library:
        logger.info("Processing Last.fm Recommendations...")
        recommendations = lastfm_client.get_recommendations()
        if recommendations:
            logger.info(f"Found {len(recommendations)} recommendations. Matching in Plex...")
            # --- TODO: Implement Track Matching & Playlist Update ---
            # matched_tracks = []
            # for rec in recommendations:
            #     plex_track = plex_client.find_track(music_library, rec['artist'], rec['title'])
            #     if plex_track:
            #         matched_tracks.append(plex_track)
            # if matched_tracks:
            #     logger.info(f"Found {len(matched_tracks)} matching tracks in Plex library.")
            #     plex_client.update_playlist(
            #         playlist_name=config.PLAYLIST_NAME_LASTFM_RECS,
            #         tracks_to_add=matched_tracks,
            #         music_library=music_library
            #     )
            # else:
            #      logger.info("No matching tracks found in Plex for Last.fm recommendations.")
            logger.warning("Placeholder: Track matching/playlist update for Last.fm Recs not yet implemented.")
        else:
            logger.info("No recommendations received from Last.fm.")
    elif config.ENABLE_LASTFM_RECS:
        logger.warning("Skipping Last.fm Recommendations: Client/Library not available or feature disabled.")

    # 2. Last.fm Charts (Placeholder)
    if config.ENABLE_LASTFM_CHARTS and lastfm_client and lastfm_client.api_key and music_library:
        logger.info("Processing Last.fm Charts...")
        # chart_tracks = lastfm_client.get_chart_top_tracks()
        # ... matching and update logic ...
        logger.warning("Placeholder: Last.fm Charts processing not yet implemented.")
    elif config.ENABLE_LASTFM_CHARTS:
         logger.warning("Skipping Last.fm Charts: Client/Library not available or feature disabled.")

    # --- Add placeholders for other playlist types later ---
    # if config.ENABLE_LISTENBRAINZ_RECS: ...
    # if config.ENABLE_TIME_PLAYLIST: ...

    logger.info("Playlist update cycle finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Phase 1 - Single Run)...")
    try:
        run_playlist_update_cycle()
    except Exception as e:
        logger.exception(f"An unexpected error occurred outside the main cycle: {e}")
    logger.info("Harmoniq service finished.")