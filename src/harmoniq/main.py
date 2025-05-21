# src/harmoniq/main.py
import logging
from datetime import datetime
import pytz # For timezone handling
# Import config variables
from . import config
# Import logger configured in log_config
from .log_config import logger
# Import Clients
from .plex_client import PlexClient
from .lastfm_client import LastfmClient

# --- Helper Function for Time Playlist ---
def get_active_time_window():
    """
    Determines the current active time window based on TIME_WINDOWS_CONFIG.
    Returns the configuration dict for the active window, or None.
    """
    if not config.TIME_WINDOWS_CONFIG:
        logger.debug("No time windows configured or parsed.")
        return None

    try:
        # Get current time in the configured timezone
        timezone = pytz.timezone(config.TIMEZONE)
        now_local = datetime.now(timezone)
        current_hour = now_local.hour
        logger.debug(f"Current local time: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z%z')}, Current Hour: {current_hour}")
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Unknown timezone: '{config.TIMEZONE}'. Defaulting to UTC for time window check.")
        now_local = datetime.now(pytz.utc)
        current_hour = now_local.hour
    except Exception as e:
        logger.error(f"Error getting current time with timezone: {e}. Defaulting to UTC.")
        now_local = datetime.now(pytz.utc)
        current_hour = now_local.hour


    for window in config.TIME_WINDOWS_CONFIG:
        start_hour = window['start_hour']
        end_hour = window['end_hour'] # Exclusive for range checks usually

        # Handle overnight windows (e.g., 22:00 - 02:00 where end_hour is < start_hour)
        if start_hour >= end_hour: # Window wraps around midnight or is a single hour (e.g. 17:00-17:00, but we use < end_hour)
                             # Corrected logic for overnight:
            if current_hour >= start_hour or current_hour < end_hour: # e.g., current 23 >= start 22 OR current 01 < end 02
                # Special case: If end_hour is 00, it means up to the end of hour 23.
                # If start_hour is 17 and end_hour is 0, this means 17,18,19,20,21,22,23.
                # The check `current_hour < end_hour` will only work if `end_hour` is e.g. 2 (for 2am).
                # If `end_hour` is 0 (representing up to midnight), we need `current_hour >= start_hour`.
                if end_hour == 0 and start_hour > 0: # Special handling for windows ending at midnight (00)
                    if current_hour >= start_hour:
                         logger.info(f"Active time window (overnight to midnight): {start_hour:02d}:00 - 00:00. Criteria: {window['criteria']}")
                         return window
                elif start_hour > end_hour: # Standard overnight (e.g., 22:00 - 05:00)
                    if current_hour >= start_hour or current_hour < end_hour:
                        logger.info(f"Active time window (overnight): {start_hour:02d}:00 - {end_hour:02d}:00. Criteria: {window['criteria']}")
                        return window
                # This should not be reached if start_hour == end_hour unless it's 00:00-00:00 (all day)
                # For now, we assume distinct start/end.

        else: # Standard window (within the same day, start_hour < end_hour)
            if start_hour <= current_hour < end_hour:
                logger.info(f"Active time window: {start_hour:02d}:00 - {end_hour:02d}:00. Criteria: {window['criteria']}")
                return window
    
    logger.info(f"No active time window found for current hour: {current_hour}")
    return None

def run_playlist_update_cycle():
    """
    Main logic loop that connects to services, fetches data,
    matches tracks, and updates Plex playlists.
    """
    logger.info("Starting playlist update cycle...")
    # Removed the debug logs from here, as config.py is parsing correctly.

    plex_client = None
    lastfm_client = None

    # --- Connect to Services ---
    try:
        plex_client = PlexClient()
        # Initialize optional clients only if enabled AND configured
        if config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS:
            if config.LASTFM_API_KEY and config.LASTFM_USER:
                 lastfm_client = LastfmClient()
            else:
                 logger.warning("Last.fm client cannot be initialized. API Key or User is missing.")
                 # No need to log disabling here, the check on `lastfm_client` instance later handles it
    except ValueError as e:
         logger.error(f"Configuration value error during client initialization: {e}. Aborting cycle.")
         return
    except Exception as e:
        logger.error(f"Failed during client initialization: {e}. Aborting update cycle.")
        return

    # --- Get Plex Libraries ---
    valid_music_libraries = []
    if plex_client:
        logger.info(f"Attempting to access Plex libraries: {config.PLEX_MUSIC_LIBRARY_NAMES}")
        for library_name in config.PLEX_MUSIC_LIBRARY_NAMES:
             library = plex_client.get_music_library(library_name)
             if library:
                 valid_music_libraries.append(library)
        if not valid_music_libraries:
             logger.error("Could not access any valid Plex music libraries defined in PLEX_MUSIC_LIBRARY_NAMES. Aborting update cycle.")
             return
        logger.info(f"Successfully accessed {len(valid_music_libraries)} Plex music libraries.")
    else:
         logger.error("Plex client not initialized. Aborting.")
         return

    target_library = valid_music_libraries[0]
    logger.info(f"Using '{target_library.title}' as the target library for creating new playlists.")

    # --- Generic function to process playlist data (for Last.fm) ---
    def process_sourced_playlist(playlist_type, fetch_func, enable_flag, playlist_name_config, size_config, client_instance):
        """Helper function to fetch from external source, match, and update a playlist."""
        if not enable_flag:
            logger.debug(f"{playlist_type} feature not enabled. Skipping.")
            return
        if not client_instance:
            logger.warning(f"Skipping {playlist_type}: Client not available (likely due to missing config).")
            return
        if not valid_music_libraries: # Should have been caught earlier, but defensive check
            logger.warning(f"Skipping {playlist_type}: No valid Plex libraries.")
            return

        logger.info(f"Processing {playlist_type}...")
        source_tracks = fetch_func(limit=size_config)
        if source_tracks:
            logger.info(f"Fetched {len(source_tracks)} tracks for {playlist_type}. Matching in Plex...")
            matched_tracks = []
            not_found_count = 0
            for i, track_data in enumerate(source_tracks):
                logger.debug(f"Matching {playlist_type} {i+1}/{len(source_tracks)}: '{track_data['artist']} - {track_data['title']}'")
                plex_track = plex_client.find_track(valid_music_libraries, track_data['artist'], track_data['title'])
                if plex_track:
                    matched_tracks.append(plex_track)
                else:
                    not_found_count += 1 # Logging of individual not founds happens in find_track
            logger.info(f"{playlist_type} Matching complete. Found {len(matched_tracks)} tracks across configured libraries. {not_found_count} tracks not found.")

            if matched_tracks:
                success = plex_client.update_playlist(
                    playlist_name=playlist_name_config,
                    tracks_to_add=matched_tracks,
                    music_library=target_library # Use first library for creation context
                )
                if success: logger.info(f"Successfully updated '{playlist_name_config}' playlist in Plex.")
                else: logger.error(f"Failed to update '{playlist_name_config}' playlist in Plex.")
            else:
                logger.info(f"No matching tracks found in Plex for {playlist_type}. Playlist '{playlist_name_config}' not created/updated.")
        else:
            logger.info(f"No tracks received from source for {playlist_type}.")

    # --- Process Last.fm Playlists ---
    process_sourced_playlist(
        playlist_type="Last.fm Recommendations (Derived)",
        fetch_func=lastfm_client.get_recommendations if lastfm_client else lambda limit: [],
        enable_flag=config.ENABLE_LASTFM_RECS,
        playlist_name_config=config.PLAYLIST_NAME_LASTFM_RECS,
        size_config=config.PLAYLIST_SIZE_LASTFM_RECS,
        client_instance=lastfm_client
    )

    process_sourced_playlist(
        playlist_type="Last.fm Charts",
        fetch_func=lastfm_client.get_chart_top_tracks if lastfm_client else lambda limit: [],
        enable_flag=config.ENABLE_LASTFM_CHARTS,
        playlist_name_config=config.PLAYLIST_NAME_LASTFM_CHARTS,
        size_config=config.PLAYLIST_SIZE_LASTFM_CHARTS,
        client_instance=lastfm_client
    )

    # --- Time-Based "Daily Flow" Playlist ---
    if config.ENABLE_TIME_PLAYLIST and plex_client and valid_music_libraries: # Ensure plex_client is available
        logger.info("Processing Time-Based 'Daily Flow' Playlist...")
        active_window = get_active_time_window()

        if active_window:
            logger.info(f"Active time window criteria: Moods={active_window['criteria']['moods']}, Styles={active_window['criteria']['styles']}")
            
            # --- TODO: Fetch tracks from Plex matching criteria ---
            # This will be a new method in plex_client.py
            # time_based_tracks = plex_client.find_tracks_by_criteria(
            #     libraries=valid_music_libraries,
            #     moods=active_window['criteria']['moods'],
            #     styles=active_window['criteria']['styles'],
            #     limit=config.PLAYLIST_SIZE_TIME 
            # )
            time_based_tracks = [] # Placeholder for now
            logger.warning("Placeholder: Actual track fetching for time-based playlist not yet implemented.")

            if time_based_tracks: # This block will only run if the placeholder is replaced with actual tracks
                logger.info(f"Found {len(time_based_tracks)} tracks for the current time window.")
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_TIME,
                    tracks_to_add=time_based_tracks,
                    music_library=target_library # Use first library for creation context
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_TIME}' playlist.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_TIME}' playlist.")
            else:
                # If placeholder is active, or no tracks found by criteria
                logger.info(f"No tracks found matching criteria (or placeholder active) for current time window. '{config.PLAYLIST_NAME_TIME}' not updated.")
        else:
            # No active window found by get_active_time_window()
            logger.info("No active time window. 'Daily Flow' playlist will not be updated.")

    elif config.ENABLE_TIME_PLAYLIST:
        # This case handles if plex_client or valid_music_libraries was None
        logger.warning("Skipping Time-Based Playlist: Plex client/libraries not available or feature disabled.")


    logger.info("Playlist update cycle finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Phase 1 - Single Run)...")
    try:
        run_playlist_update_cycle()
    except Exception as e:
        logger.exception(f"An unexpected error occurred during the main update cycle: {e}")
    finally:
        logger.info("Harmoniq service finished.")