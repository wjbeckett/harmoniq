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
    lb_client = None

    # --- Connect to Services ---
    try:
        plex_client = PlexClient() # Essential
        # Initialize optional clients only if enabled AND configured
        if config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS:
            if config.LASTFM_API_KEY and config.LASTFM_USER:
                 lastfm_client = LastfmClient()
            else:
                 logger.warning("Last.fm client cannot be initialized. API Key or User is missing.")
                 if config.ENABLE_LASTFM_RECS: logger.warning("Disabling Last.fm Recommendations.")
                 if config.ENABLE_LASTFM_CHARTS: logger.warning("Disabling Last.fm Charts.")

    except ValueError as e:
         logger.error(f"Configuration value error during client initialization: {e}. Aborting cycle.")
         return
    except Exception as e:
        logger.error(f"Failed during client initialization: {e}. Aborting update cycle.")
        return

    # --- Get Plex Libraries ---
    valid_music_libraries = [] # Store the actual LibrarySection objects
    if plex_client:
        logger.info(f"Attempting to access Plex libraries: {config.PLEX_MUSIC_LIBRARY_NAMES}")
        for library_name in config.PLEX_MUSIC_LIBRARY_NAMES:
             library = plex_client.get_music_library(library_name) # Use the updated client method
             if library:
                 valid_music_libraries.append(library)
             # Warnings/errors logged within get_music_library if not found/valid

        if not valid_music_libraries:
             logger.error("Could not access any valid Plex music libraries defined in PLEX_MUSIC_LIBRARY_NAMES. Aborting update cycle.")
             return
        logger.info(f"Successfully accessed {len(valid_music_libraries)} Plex music libraries.")
    else:
         logger.error("Plex client not initialized. Aborting.")
         return


    # --- Target Library for Playlist Creation ---
    # Use the first valid music library found as the default context for creating new playlists.
    target_library = valid_music_libraries[0]
    logger.info(f"Using '{target_library.title}' as the target library for creating new playlists.")

    # --- Process Enabled Playlist Types ---
    # 1. Last.fm Recommendations
    if config.ENABLE_LASTFM_RECS and lastfm_client and valid_music_libraries: # Check for lastfm_client instance
        logger.info("Processing Last.fm Recommendations (Derived)...")
        recommendations_fm = lastfm_client.get_recommendations(limit=config.PLAYLIST_SIZE_LASTFM_RECS)
        if recommendations_fm:
            logger.info(f"Fetched {len(recommendations_fm)} derived recommendations. Matching in Plex...")

            matched_tracks_fm = []
            not_found_count_fm = 0
            for i, rec in enumerate(recommendations_fm):
                logger.debug(f"Matching FM-Rec {i+1}/{len(recommendations_fm)}: '{rec['artist']} - {rec['title']}'")
                # Pass the LIST of libraries
                plex_track = plex_client.find_track(valid_music_libraries, rec['artist'], rec['title'])
                if plex_track:
                    matched_tracks_fm.append(plex_track)
                else:
                    not_found_count_fm += 1

            logger.info(f"Last.fm Rec Matching complete. Found {len(matched_tracks_fm)} tracks across configured libraries. {not_found_count_fm} recommended tracks not found.")

            if matched_tracks_fm:
                # Pass the TARGET library
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_LASTFM_RECS,
                    tracks_to_add=matched_tracks_fm,
                    music_library=target_library
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_LASTFM_RECS}' playlist in Plex.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_LASTFM_RECS}' playlist in Plex.")
            else:
                 logger.info("No matching tracks found in Plex for Last.fm recommendations. Playlist not created/updated.")
        else:
            logger.info("No derived recommendations generated from Last.fm.")
    elif config.ENABLE_LASTFM_RECS:
        logger.warning("Skipping Last.fm Recommendations: Client not available, no valid libraries, or feature disabled.")


    # 2. Last.fm Charts (Optional)
    if config.ENABLE_LASTFM_CHARTS and lastfm_client and valid_music_libraries: # Check for lastfm_client instance
        logger.info("Processing Last.fm Charts...")
        chart_tracks_data = lastfm_client.get_chart_top_tracks(limit=config.PLAYLIST_SIZE_LASTFM_CHARTS)
        if chart_tracks_data:
            logger.info(f"Fetched {len(chart_tracks_data)} chart tracks. Matching in Plex...")

            matched_chart_tracks = []
            not_found_chart_count = 0
            for i, track_data in enumerate(chart_tracks_data):
                 logger.debug(f"Matching chart {i+1}/{len(chart_tracks_data)}: '{track_data['artist']} - {track_data['title']}'")
                 # Pass the LIST of libraries
                 plex_track = plex_client.find_track(valid_music_libraries, track_data['artist'], track_data['title'])
                 if plex_track:
                     matched_chart_tracks.append(plex_track)
                 else:
                     not_found_chart_count += 1

            logger.info(f"Matching complete for charts. Found {len(matched_chart_tracks)} tracks across configured libraries. {not_found_chart_count} chart tracks not found.")

            if matched_chart_tracks:
                # Pass the TARGET library
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_LASTFM_CHARTS,
                    tracks_to_add=matched_chart_tracks,
                    music_library=target_library
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_LASTFM_CHARTS}' playlist in Plex.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_LASTFM_CHARTS}' playlist in Plex.")
            else:
                 logger.info("No matching tracks found in Plex for Last.fm chart tracks. Playlist not created/updated.")
        else:
             logger.info("No chart tracks received from Last.fm.")
    elif config.ENABLE_LASTFM_CHARTS:
         logger.warning("Skipping Last.fm Charts: Client not available, no valid libraries, or feature disabled.")


    # --- Add placeholders for other playlist types later ---
    # if config.ENABLE_TIME_PLAYLIST and valid_music_libraries: ...

    logger.info("Playlist update cycle finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Phase 1 - Single Run)...")
    try:
        # Config loading happens on import, errors there will exit the script
        run_playlist_update_cycle()
    except Exception as e:
        # Catch errors happening during the cycle itself that weren't caught internally
        logger.exception(f"An unexpected error occurred during the main update cycle: {e}")
    finally:
        # This ensures the finished message is logged even if errors occur
        logger.info("Harmoniq service finished.")