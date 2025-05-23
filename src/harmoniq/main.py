# src/harmoniq/main.py
import logging
from datetime import datetime
import pytz
from . import config # config.py now parses SCHEDULED_PERIODS
from .log_config import logger
from .plex_client import PlexClient
from .lastfm_client import LastfmClient

# --- Helper Function to get current active period details ---
def get_active_period_details() -> dict | None:
    """
    Determines the current active named period and its details (start_hour, criteria)
    based on the SCHEDULED_PERIODS from config.py.
    The last period defined before the current hour is considered active.
    Handles wrap-around for the first period of the day.
    """
    if not config.SCHEDULED_PERIODS: # This is populated by config.py
        logger.debug("No scheduled periods configured or parsed.")
        return None

    try:
        timezone = pytz.timezone(config.TIMEZONE)
        now_local = datetime.now(timezone)
        current_hour = now_local.hour
        logger.debug(f"Current local time for period check: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z%z')}, Current Hour: {current_hour}")
    except Exception as e:
        logger.error(f"Error getting current time with timezone '{config.TIMEZONE}': {e}. Defaulting to UTC.")
        now_local = datetime.now(pytz.utc); current_hour = now_local.hour

    # SCHEDULED_PERIODS is already sorted by start_hour in config.py
    active_period = None
    
    # Find the latest period that has started but is not past the current hour
    # If current_hour is before the first scheduled period's start_hour, it means we're in the "last" period of the previous day
    # which wraps around.
    
    if not config.SCHEDULED_PERIODS: # Should not happen if config parsing worked
        return None

    # Default to the last period in the schedule (handles wrap-around for early morning hours)
    active_period = config.SCHEDULED_PERIODS[-1] 

    for period_details in config.SCHEDULED_PERIODS:
        if period_details['start_hour'] <= current_hour:
            active_period = period_details
        else:
            # We've passed the current hour, so the *previous* period was the correct one
            break 
            # This break is important because SCHEDULED_PERIODS is sorted by start_hour

    if active_period:
        logger.info(f"Active period identified: '{active_period['name']}' (starts {active_period['start_hour']:02d}:00). Criteria: {active_period['criteria']}")
        return active_period
    else:
        # This case should ideally not be hit if SCHEDULED_PERIODS is populated,
        # as we default to the last period. But as a fallback:
        logger.warning(f"Could not determine active period for current hour: {current_hour}. Using fallback 'DefaultVibe'.")
        return {
            'name': 'DefaultVibe', 
            'start_hour': current_hour, # Not strictly accurate but for context
            'criteria': config.DEFAULT_PERIOD_VIBES.get("DefaultVibe", {"moods":[], "styles":[]})
            }

# --- Generic function to process playlist data from external sources (Last.fm) ---
# (This _process_sourced_playlist helper function remains the same as your last version)
def _process_sourced_playlist(plex_client, valid_music_libraries, target_library, playlist_type, fetch_func, enable_flag, playlist_name_config, size_config, client_instance):
    if not enable_flag: logger.debug(f"{playlist_type} feature not enabled. Skipping."); return
    if not client_instance: logger.warning(f"Skipping {playlist_type}: Client not available."); return
    if not valid_music_libraries: logger.warning(f"Skipping {playlist_type}: No valid Plex libraries."); return

    logger.info(f"Processing {playlist_type}...")
    source_tracks = fetch_func(limit=size_config)
    if source_tracks:
        logger.info(f"Fetched {len(source_tracks)} tracks for {playlist_type}. Matching in Plex...")
        matched_tracks = []; not_found_count = 0
        for i, track_data in enumerate(source_tracks):
            logger.debug(f"Matching {playlist_type} {i+1}/{len(source_tracks)}: '{track_data['artist']} - {track_data['title']}'")
            plex_track = plex_client.find_track(valid_music_libraries, track_data['artist'], track_data['title'])
            if plex_track: matched_tracks.append(plex_track)
            else: not_found_count +=1
        logger.info(f"{playlist_type} Matching complete. Found {len(matched_tracks)}. {not_found_count} not found.")
        if matched_tracks:
            if plex_client.update_playlist(playlist_name_config, matched_tracks, target_library): logger.info(f"Successfully updated '{playlist_name_config}'.")
            else: logger.error(f"Failed to update '{playlist_name_config}'.")
        else: logger.info(f"No matching tracks for {playlist_type}. Playlist '{playlist_name_config}' not updated.")
    else: logger.info(f"No tracks from source for {playlist_type}.")


# --- Function specifically for Harmoniq Flow update ---
# Now accepts active_period_details directly from the scheduler
def run_harmoniq_flow_update(plex_client: PlexClient, valid_music_libraries: list, target_library, active_period_details: dict | None):
    """Handles the update logic for the Time-Based 'Harmoniq Flow' Playlist."""
    if not (config.ENABLE_TIME_PLAYLIST and plex_client and valid_music_libraries):
        logger.info("Skipping Harmoniq Flow: Feature disabled or Plex client/libraries not available.")
        return

    if not active_period_details: # Get details if not passed (e.g., for manual run)
        active_period_details = get_active_period_details() 

    if active_period_details:
        period_name = active_period_details['name']
        moods_to_match = active_period_details['criteria']['moods']
        styles_to_match = active_period_details['criteria']['styles']
        
        logger.info(f"Processing Harmoniq Flow for period '{period_name}'...")
        logger.info(f"Period criteria: Moods={moods_to_match}, Styles/Genres={styles_to_match}")
        
        time_based_tracks = plex_client.find_tracks_by_criteria( # This is the method we've been working on
            libraries=valid_music_libraries,
            moods=moods_to_match,
            styles=styles_to_match, # Treated as genres in find_tracks_by_criteria
            limit=config.PLAYLIST_SIZE_TIME
        )

        if time_based_tracks:
            logger.info(f"Found {len(time_based_tracks)} tracks for the '{period_name}' period.")
            success = plex_client.update_playlist(
                playlist_name=config.PLAYLIST_NAME_TIME, # Use the single Harmoniq Flow playlist name
                tracks_to_add=time_based_tracks,
                music_library=target_library
            )
            if success: logger.info(f"Successfully updated '{config.PLAYLIST_NAME_TIME}' playlist for '{period_name}'.")
            else: logger.error(f"Failed to update '{config.PLAYLIST_NAME_TIME}' playlist for '{period_name}'.")
        else:
            logger.info(f"No tracks found matching criteria for '{period_name}'. '{config.PLAYLIST_NAME_TIME}' not updated.")
    else:
        logger.info("No active time period determined. 'Harmoniq Flow' playlist will not be updated.")


# --- Function specifically for Last.fm and other external services ---
def run_external_services_update(plex_client: PlexClient, lastfm_client: LastfmClient | None, valid_music_libraries: list, target_library):
    """Handles updates for playlists sourced from Last.fm etc."""
    # (This function remains the same as your last version)
    if not (plex_client and valid_music_libraries):
         logger.error("Plex client or libraries not available for external services update. Skipping.")
         return
    logger.info("Processing External Service Playlists (Last.fm)...")
    _process_sourced_playlist(plex_client, valid_music_libraries, target_library, "Last.fm Recommendations (Derived)", lastfm_client.get_recommendations if lastfm_client else lambda l:[], config.ENABLE_LASTFM_RECS, config.PLAYLIST_NAME_LASTFM_RECS, config.PLAYLIST_SIZE_LASTFM_RECS, lastfm_client)
    _process_sourced_playlist(plex_client, valid_music_libraries, target_library, "Last.fm Charts", lastfm_client.get_chart_top_tracks if lastfm_client else lambda l:[], config.ENABLE_LASTFM_CHARTS, config.PLAYLIST_NAME_LASTFM_CHARTS, config.PLAYLIST_SIZE_LASTFM_CHARTS, lastfm_client)
    logger.info("External Service Playlists update finished.")


# --- Combined function for single run (useful for if __name__ == "__main__") ---
def run_all_updates_once():
    logger.info("Starting all playlist update cycles (single run)...")
    plex_client = None; lastfm_client = None
    try:
        plex_client = PlexClient()
        if config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS:
            if config.LASTFM_API_KEY and config.LASTFM_USER: lastfm_client = LastfmClient()
            else: logger.warning("Last.fm client not initialized (API Key/User missing) for single run.")
    except Exception as e: logger.error(f"Failed during client initialization for single run: {e}. Aborting."); return

    valid_music_libraries = []
    if plex_client:
        for name in config.PLEX_MUSIC_LIBRARY_NAMES:
             lib = plex_client.get_music_library(name)
             if lib: valid_music_libraries.append(lib)
        if not valid_music_libraries: logger.error("No valid Plex music libraries for single run. Aborting."); return
    else: logger.error("Plex client not initialized for single run. Aborting."); return
    
    target_library = valid_music_libraries[0]

    # For a single manual run, get the current active period and run flow update
    active_period = get_active_period_details()
    if active_period:
        run_harmoniq_flow_update(plex_client, valid_music_libraries, target_library, active_period) # Pass active_period
    else:
        logger.warning("Manual run: No active period identified, skipping Harmoniq Flow update.")
        
    run_external_services_update(plex_client, lastfm_client, valid_music_libraries, target_library)
    
    logger.info("All playlist update cycles (single run) finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Manual Single Run via main.py)...")
    try:
        run_all_updates_once()
    except Exception as e:
        logger.exception(f"An unexpected error occurred during the manual run: {e}")
    finally:
        logger.info("Harmoniq manual run finished.")