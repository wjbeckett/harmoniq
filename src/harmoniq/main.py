# src/harmoniq/main.py
import os
import logging
from datetime import datetime
import pytz
from . import config
from .log_config import logger
from .plex_client import PlexClient
from .lastfm_client import LastfmClient
from .image_utils import generate_playlist_cover

# --- Helper Function to get current active period details ---
def get_active_period_details() -> dict | None:
    if not config.SCHEDULED_PERIODS: 
        logger.debug("No scheduled periods configured or parsed.")
        return None
    try:
        tz = pytz.timezone(config.TIMEZONE)
        now_local = datetime.now(tz)
        current_hour = now_local.hour
        logger.debug(f"Current local time for period check: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z%z')}, Current Hour: {current_hour}")
    except Exception as e:
        logger.error(f"Error getting current time with timezone '{config.TIMEZONE}': {e}. Defaulting to UTC.")
        now_local = datetime.now(pytz.utc)
        current_hour = now_local.hour

    active_period_candidate = None
    
    # SCHEDULED_PERIODS is sorted by start_hour in config.py
    # Find the latest period that has started
    for p_details in config.SCHEDULED_PERIODS:
        if p_details['start_hour'] <= current_hour:
            active_period_candidate = p_details
        elif active_period_candidate is None and p_details['start_hour'] > current_hour:
            # If current hour is before the first scheduled period, use the last period of the day (wraparound)
            active_period_candidate = config.SCHEDULED_PERIODS[-1]
            break 
        elif p_details['start_hour'] > current_hour:
            # We've passed current_hour, so the previous candidate was correct
            break
            
    # If loop finishes and active_period_candidate is still None (e.g., empty SCHEDULED_PERIODS after all),
    # or if current hour is before the first period in a non-empty list.
    if active_period_candidate is None and config.SCHEDULED_PERIODS:
        active_period_candidate = config.SCHEDULED_PERIODS[-1] # Default to last for wraparound
    
    if active_period_candidate:
        # Calculate the set of hours for this active period
        period_name = active_period_candidate['name']
        start_h = active_period_candidate['start_hour']
        
        current_period_index = -1
        for i, p_conf in enumerate(config.SCHEDULED_PERIODS):
            if p_conf['name'] == period_name:
                current_period_index = i
                break
        
        end_h_exclusive = 24 # Default to end of day
        if current_period_index != -1 : # Should always be found
            if current_period_index + 1 < len(config.SCHEDULED_PERIODS):
                end_h_exclusive = config.SCHEDULED_PERIODS[current_period_index + 1]['start_hour']
            else: # This is the last defined period, so it runs until the first period of the next day
                end_h_exclusive = config.SCHEDULED_PERIODS[0]['start_hour'] 
                # If end_h_exclusive is <= start_h, it means it wraps around midnight.
                # If it wraps, hours are start_h..23 and 0..end_h_exclusive-1
                # If it doesn't wrap past first period (e.g. last period 22:00, first is 05:00), it effectively means up to 24:00 (exclusive)
                if end_h_exclusive > start_h : end_h_exclusive = 24 # Not wrapping past midnight to next day's first period start time

        active_hours_set = set()
        if start_h < end_h_exclusive: # Normal day segment or ends at midnight (represented as 24)
            for h_loop in range(start_h, end_h_exclusive):
                active_hours_set.add(h_loop)
        else: # Overnight segment (e.g. 22:00 start, next period starts at 05:00 next day)
            for h_loop in range(start_h, 24): 
                active_hours_set.add(h_loop)
            for h_loop in range(0, end_h_exclusive): 
                active_hours_set.add(h_loop)
        
        # Create a copy to add 'hours_set' to, to avoid modifying the global config.SCHEDULED_PERIODS items
        return_period_details = active_period_candidate.copy()
        return_period_details['hours_set'] = active_hours_set
        logger.info(f"Active period: '{period_name}' (Starts {start_h:02d}:00). Effective Hours: {sorted(list(active_hours_set))}. Criteria: {return_period_details['criteria']}")
        return return_period_details
    else:
        logger.warning(f"Could not determine active period for current hour: {current_hour}. Using fallback 'DefaultVibe'.")
        return { 
            'name': 'DefaultVibe', 'start_hour': current_hour, 
            'criteria': config.DEFAULT_PERIOD_VIBES.get("DefaultVibe", {"moods":[], "styles":[]}),
            'hours_set': set(range(24)) 
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
        # Pass None for active_period_name for non-time-based playlists
            if plex_client.update_playlist(playlist_name_config, matched_tracks, target_library, active_period_name=None): 
                logger.info(f"Successfully updated '{playlist_name_config}'.")
            else: 
                logger.error(f"Failed to update '{playlist_name_config}'.")
        else: logger.info(f"No matching tracks for {playlist_type}. Playlist '{playlist_name_config}' not updated.")
    else: logger.info(f"No tracks from source for {playlist_type}.")


# --- Function specifically for Harmoniq Flow update ---
def run_harmoniq_flow_update(plex_client: PlexClient, valid_music_libraries: list, target_library, active_period_details: dict | None):
    """Handles the update logic for the Time-Based 'Harmoniq Flow' Playlist."""
    if not (config.ENABLE_TIME_PLAYLIST and plex_client and valid_music_libraries):
        logger.info("Skipping Harmoniq Flow: Feature disabled or Plex client/libraries not available.")
        return

    if not active_period_details: 
        active_period_details = get_active_period_details() 

    if active_period_details and 'hours_set' in active_period_details:
        period_name = active_period_details['name']
        # These are the BASE target moods/styles from config (default or user TP_DEFINE_ override)
        # The generate_harmoniq_flow_playlist method will handle learning/augmentation internally
        base_target_moods = active_period_details['criteria']['moods']
        base_target_styles = active_period_details['criteria']['styles']
        period_hours_set = active_period_details['hours_set']
        
        # The main processing, including vibe learning, is now inside generate_harmoniq_flow_playlist
        logger.info(f"Processing Harmoniq Flow for period '{period_name}' using base criteria (learning will happen in PlexClient)...")
        # logger.info(f"Base Period Criteria: Moods={base_target_moods}, Styles/Genres={base_target_styles}, Effective Hours={sorted(list(period_hours_set))}")
        
        time_based_tracks = plex_client.generate_harmoniq_flow_playlist(
            libraries=valid_music_libraries, 
            active_period_name=period_name,
            base_target_moods=base_target_moods,   # Pass BASE moods
            base_target_styles=base_target_styles, # Pass BASE styles
            period_active_hours=period_hours_set, 
            playlist_target_size=config.PLAYLIST_SIZE_TIME
        )

        if time_based_tracks:
            logger.info(f"Generated {len(time_based_tracks)} tracks for the '{period_name}' period for playlist update.")
            playlist_updated = plex_client.update_playlist(
                config.PLAYLIST_NAME_TIME, 
                time_based_tracks, 
                target_library,
                active_period_name=period_name,
            )
            
            if playlist_updated:
                logger.info(f"Successfully updated '{config.PLAYLIST_NAME_TIME}' for '{period_name}'.")
                if config.ENABLE_PLAYLIST_COVERS:
                    logger.info("Attempting to generate and upload playlist cover...")
                    cover_image_path = generate_playlist_cover(
                        playlist_title=config.PLAYLIST_NAME_TIME,
                        period_name=period_name,
                        active_moods=base_target_moods, 
                        active_styles=base_target_styles
                    )
                    
                    if cover_image_path and os.path.exists(cover_image_path): # os is available here
                        try:
                            plex_playlist_obj = plex_client.plex.playlist(config.PLAYLIST_NAME_TIME)
                            if plex_playlist_obj:
                                plex_client.upload_playlist_cover(plex_playlist_obj, cover_image_path)
                            else: 
                                logger.warning(f"Could not retrieve playlist '{config.PLAYLIST_NAME_TIME}' to upload cover.")
                        except Exception as e_cover_upload: 
                            # --- MODIFIED LOGGING HERE ---
                            logger.error(f"Caught exception during cover retrieval/upload. Error: {e_cover_upload}")
                            logger.exception("Full traceback for cover upload failure:") # This will print the traceback
                            # --- END MODIFIED LOGGING ---
                        finally:
                            # ... (finally block with os.path.exists and os.remove - this part seems to work) ...
                            logger.debug(f"DEBUG_OS: Type of 'os' in finally: {type(os)}")
                            logger.debug(f"DEBUG_OS: os.path.exists available: {hasattr(os, 'path') and hasattr(os.path, 'exists')}")
                            if os.path.exists(config.COVER_OUTPUT_PATH):
                                try: 
                                    os.remove(config.COVER_OUTPUT_PATH)
                                    logger.debug(f"Temp cover '{config.COVER_OUTPUT_PATH}' removed.")
                                except OSError as e_remove: 
                                    logger.warning(f"Could not remove temp cover '{config.COVER_OUTPUT_PATH}': {e_remove}")
                            else:
                                logger.debug(f"DEBUG_OS: Temp cover file {config.COVER_OUTPUT_PATH} does not exist for removal (or os.path.exists failed).")
            else: logger.error(f"Failed to update '{config.PLAYLIST_NAME_TIME}' for '{period_name}', cover not generated.")
        else:
            logger.info(f"No tracks generated for '{period_name}'. '{config.PLAYLIST_NAME_TIME}' not updated.")
    elif active_period_details and 'hours_set' not in active_period_details:
        logger.error(f"Active period details for '{active_period_details.get('name')}' missing 'hours_set'.")
    else:
        logger.info("No active time period. 'Harmoniq Flow' playlist not updated.")


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