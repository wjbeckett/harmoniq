# src/harmoniq/config.py
import os
import logging
from dotenv import load_dotenv
import re # Import regex

load_dotenv()
logger = logging.getLogger(__name__)

# (get_env_var helper function remains the same)
def get_env_var(var_name, default=None, required=False, var_type=str):
    value = os.environ.get(var_name, default)
    if required and value is None:
        logger.error(f"Missing required environment variable: {var_name}")
        raise ValueError(f"Missing required environment variable: {var_name}")
    if value is not None:
        try:
            if var_type == bool:
                if isinstance(value, str):
                    return value.lower() in ['true', '1', 'yes']
                return bool(value)
            elif var_type == list:
                 if isinstance(value, str):
                     # Remove empty strings that might result from trailing commas etc.
                     return [item.strip() for item in value.split(',') if item.strip()]
                 elif isinstance(value, list):
                     return value
                 else:
                     raise ValueError("List type must be a comma-separated string.")
            return var_type(value)
        except ValueError as e:
            logger.error(f"Invalid type for environment variable: {var_name}. Expected {var_type}, got '{value}'. Error: {e}")
            raise ValueError(f"Invalid type for environment variable: {var_name}")
    return default

# --- Load Configuration Settings ---
try:
    # ... (Plex, Scheduling, Last.fm vars remain the same) ...
    PLEX_URL = get_env_var("PLEX_URL", required=True)
    PLEX_TOKEN = get_env_var("PLEX_TOKEN", required=True)
    PLEX_MUSIC_LIBRARY_NAMES = get_env_var("PLEX_MUSIC_LIBRARY_NAMES", default="Music", required=True, var_type=list)
    RUN_INTERVAL_MINUTES = get_env_var("RUN_INTERVAL_MINUTES", default=1440, var_type=int)
    TIMEZONE = get_env_var("TIMEZONE", default="UTC")
    LASTFM_API_KEY = get_env_var("LASTFM_API_KEY")
    LASTFM_USER = get_env_var("LASTFM_USER")

    # Feature Flags
    ENABLE_LASTFM_RECS = get_env_var("ENABLE_LASTFM_RECS", default=True, var_type=bool)
    ENABLE_LASTFM_CHARTS = get_env_var("ENABLE_LASTFM_CHARTS", default=True, var_type=bool)
    ENABLE_TIME_PLAYLIST = get_env_var("ENABLE_TIME_PLAYLIST", default=True, var_type=bool)

    # Playlist Naming
    PLAYLIST_NAME_LASTFM_RECS = get_env_var("PLAYLIST_NAME_LASTFM_RECS", "Last.fm Discovery")
    PLAYLIST_NAME_LASTFM_CHARTS = get_env_var("PLAYLIST_NAME_LASTFM_CHARTS", "Last.fm Global Charts")
    PLAYLIST_NAME_TIME = get_env_var("PLAYLIST_NAME_TIME", "Daily Flow")

    # Playlist Sizing
    PLAYLIST_SIZE_LASTFM_RECS = get_env_var("PLAYLIST_SIZE_LASTFM_RECS", 30, var_type=int)
    PLAYLIST_SIZE_LASTFM_CHARTS = get_env_var("PLAYLIST_SIZE_LASTFM_CHARTS", 50, var_type=int)
    PLAYLIST_SIZE_TIME = get_env_var("PLAYLIST_SIZE_TIME", 40, var_type=int)

    # --- Time Playlist Configuration Parsing (REVISED LOGIC) ---
    TIME_WINDOWS_RAW = get_env_var("TIME_WINDOWS", default="")
    TIME_WINDOWS_CONFIG = []
    # Regex to specifically match the time part HH:MM-HH:MM at the beginning
    time_regex = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")

    if ENABLE_TIME_PLAYLIST and TIME_WINDOWS_RAW:
        logger.info("Parsing TIME_WINDOWS configuration...")
        # Split by semicolon initially
        parts = [p.strip() for p in TIME_WINDOWS_RAW.strip().split(';') if p.strip()]

        current_window_data = None

        for part in parts:
            time_match = time_regex.match(part)

            if time_match:
                # --- Start of a new window definition ---
                # 1. Finalize the previous window if it exists
                if current_window_data:
                    if not any(current_window_data['criteria'].values()):
                         logger.warning(f"Finalizing window starting {current_window_data['start_hour']}:00, but no valid criteria were found. Skipping window.")
                    else:
                         logger.debug(f"Finalizing window: Start={current_window_data['start_hour']}, End={current_window_data['end_hour']}, Criteria={current_window_data['criteria']}")
                         TIME_WINDOWS_CONFIG.append(current_window_data)

                # 2. Parse the new time range
                start_h, start_m, end_h, end_m = map(int, time_match.groups())
                if not (0 <= start_h < 24 and 0 <= start_m < 60 and 0 <= end_h < 24 and 0 <= end_m < 60):
                    logger.warning(f"Skipping invalid time window definition (invalid hour/minute values): '{part}'")
                    current_window_data = None # Discard current if time is invalid
                    continue
                start_hour = start_h
                end_hour = end_h # Exclusive

                # 3. Initialize data for the new window
                current_window_data = {
                    'start_hour': start_hour,
                    'end_hour': end_hour,
                    'criteria': {'moods': [], 'styles': []} # Initialize criteria dict
                }

                # 4. Check if there are criteria attached to this same part (after the time and ':')
                criteria_str_part = part[time_match.end():].lstrip(':').strip()
                if criteria_str_part:
                    # Parse these initial criteria
                    if '=' in criteria_str_part:
                        key, value_str = criteria_str_part.split('=', 1)
                        key = key.strip().lower()
                        values = [v.strip().capitalize() for v in value_str.split(',') if v.strip()]
                        if key in current_window_data['criteria'] and values:
                            current_window_data['criteria'][key].extend(values)
                            logger.debug(f"Parsed initial criteria for window starting {start_hour}:00 : {key}={values}")
                        else:
                            logger.warning(f"Invalid initial criteria format or unknown key '{key}' in part: '{criteria_str_part}'")
                    else:
                         logger.warning(f"Invalid initial criteria format (missing '=') in part: '{criteria_str_part}'")

            elif current_window_data:
                # --- Continuation of criteria for the current window ---
                if '=' in part:
                    key, value_str = part.split('=', 1)
                    key = key.strip().lower()
                    values = [v.strip().capitalize() for v in value_str.split(',') if v.strip()]
                    if key in current_window_data['criteria'] and values:
                        current_window_data['criteria'][key].extend(values)
                        logger.debug(f"Parsed additional criteria for window starting {current_window_data['start_hour']}:00 : {key}={values}")
                    else:
                        logger.warning(f"Invalid criteria format or unknown key '{key}' in part: '{part}' for window starting {current_window_data['start_hour']}:00")
                else:
                    logger.warning(f"Invalid criteria format (missing '=') in part: '{part}' for window starting {current_window_data['start_hour']}:00")
            else:
                # This part is not a time definition and we don't have an active window
                logger.warning(f"Skipping definition part '{part}' as it's not a time range and no window is active.")

        # --- Finalize the very last window after the loop ---
        if current_window_data:
            if not any(current_window_data['criteria'].values()):
                 logger.warning(f"Finalizing last window starting {current_window_data['start_hour']}:00, but no valid criteria were found. Skipping window.")
            else:
                 logger.debug(f"Finalizing last window: Start={current_window_data['start_hour']}, End={current_window_data['end_hour']}, Criteria={current_window_data['criteria']}")
                 TIME_WINDOWS_CONFIG.append(current_window_data)


        # --- Post-parsing validation ---
        if not TIME_WINDOWS_CONFIG:
             logger.warning("ENABLE_TIME_PLAYLIST is true, but no valid TIME_WINDOWS definitions were successfully parsed. Time playlist will not be generated.")
             # ENABLE_TIME_PLAYLIST = False # Optionally disable
        else:
             # Sanity check for overlapping hours could be added here if needed
             logger.info(f"Successfully parsed {len(TIME_WINDOWS_CONFIG)} time window definitions.")


    elif ENABLE_TIME_PLAYLIST:
         logger.warning("ENABLE_TIME_PLAYLIST is true, but TIME_WINDOWS environment variable is empty or missing. Time playlist will not be generated.")
         # ENABLE_TIME_PLAYLIST = False # Optionally disable

    # Logging Level
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

    # --- Post-load Validation ---
    if (ENABLE_LASTFM_RECS or ENABLE_LASTFM_CHARTS) and (not LASTFM_API_KEY or not LASTFM_USER):
        logger.warning("Last.fm features enabled but LASTFM_API_KEY or LASTFM_USER is missing. Last.fm features will be disabled.")

    logger.info("Configuration loaded successfully.")
    # (DEBUG logging...)

except ValueError as e: logger.error(f"Configuration error: {e}"); raise SystemExit(f"Configuration error: {e}")
except Exception as e: logger.exception(f"Unexpected error during configuration loading: {e}"); raise SystemExit(f"Unexpected configuration loading error: {e}")