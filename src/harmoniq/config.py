# src/harmoniq/config.py
import os
import logging
from dotenv import load_dotenv
import re

# Load .env file if it exists (primarily for local development)
load_dotenv()

logger = logging.getLogger(__name__) # Use the logger configured in log_config

# Helper function to get environment variables
def get_env_var(var_name, default=None, required=False, var_type=str):
    # ... (keep existing helper function) ...
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
            # Special handling for list type from comma-separated string
            elif var_type == list:
                if isinstance(value, str):
                    return [item.strip() for item in value.split(',') if item.strip()]
                elif isinstance(value, list): # Already a list (less likely from env)
                    return value
                else:
                    raise ValueError("List type must be a comma-separated string.")
            return var_type(value)
        except ValueError as e:
            logger.error(f"Invalid type for environment variable: {var_name}. Expected {var_type}, got '{value}'. Error: {e}")
            raise ValueError(f"Invalid type for environment variable: {var_name}")
    return default # Return None or the default if not required and not set, or already correct type

# --- Load Configuration Settings ---
try:
    # Plex
    PLEX_URL = get_env_var("PLEX_URL", required=True)
    PLEX_TOKEN = get_env_var("PLEX_TOKEN", required=True)
    # Allow multiple library names, comma-separated
    PLEX_MUSIC_LIBRARY_NAMES = get_env_var("PLEX_MUSIC_LIBRARY_NAMES", default="Music", required=True, var_type=list)

    # Scheduling & Timezone
    RUN_INTERVAL_MINUTES = get_env_var("RUN_INTERVAL_MINUTES", default=1440, var_type=int)
    TIMEZONE = get_env_var("TIMEZONE", default="UTC")

    # Last.fm (Required only if enabled)
    LASTFM_API_KEY = get_env_var("LASTFM_API_KEY")
    LASTFM_USER = get_env_var("LASTFM_USER")

    # Feature Flags (Defaults adjusted)
    ENABLE_LASTFM_RECS = get_env_var("ENABLE_LASTFM_RECS", default=False, var_type=bool) # Default OFF
    ENABLE_LASTFM_CHARTS = get_env_var("ENABLE_LASTFM_CHARTS", default=True, var_type=bool) # Default ON
    ENABLE_TIME_PLAYLIST = get_env_var("ENABLE_TIME_PLAYLIST", default=False, var_type=bool)
    # ENABLE_CUSTOM_1 = get_env_var("ENABLE_CUSTOM_1", default=False, var_type=bool)

    # Playlist Naming
    PLAYLIST_NAME_LASTFM_RECS = get_env_var("PLAYLIST_NAME_LASTFM_RECS", "Last.fm Discovery")
    PLAYLIST_NAME_LASTFM_CHARTS = get_env_var("PLAYLIST_NAME_LASTFM_CHARTS", "Last.fm Global Charts")
    PLAYLIST_NAME_TIME = get_env_var("PLAYLIST_NAME_TIME", "Daily Flow")
    # PLAYLIST_NAME_CUSTOM_1 = get_env_var("PLAYLIST_NAME_CUSTOM_1", "My Custom Playlist")

    # Playlist Sizing
    PLAYLIST_SIZE_LASTFM_RECS = get_env_var("PLAYLIST_SIZE_LASTFM_RECS", 30, var_type=int)
    PLAYLIST_SIZE_LASTFM_CHARTS = get_env_var("PLAYLIST_SIZE_LASTFM_CHARTS", 50, var_type=int)
    PLAYLIST_SIZE_TIME = get_env_var("PLAYLIST_SIZE_TIME", 40, var_type=int)
    # PLAYLIST_SIZE_CUSTOM_1 = get_env_var("PLAYLIST_SIZE_CUSTOM_1", 25, var_type=int)

    TIME_WINDOWS_RAW = get_env_var("TIME_WINDOWS", default="") # Example: "00:00-06:00:moods=Calm,Mellow;06:00-12:00:moods=Energetic,Upbeat;styles=Pop,Rock"
    TIME_WINDOWS_CONFIG = [] # Parsed structure: [{'start': 0, 'end': 6, 'criteria': {'moods': ['Calm', 'Mellow']}}, ...]

    if ENABLE_TIME_PLAYLIST and TIME_WINDOWS_RAW:
        logger.info("Parsing TIME_WINDOWS configuration...")
        window_defs = TIME_WINDOWS_RAW.strip().split(';')
        for i, window_def in enumerate(window_defs):
            if not window_def: continue
            parts = window_def.split(':', 2) # Split into max 3 parts: time, criteria
            if len(parts) < 2:
                logger.warning(f"Skipping invalid time window definition (missing time or criteria): '{window_def}'")
                continue

            # Parse Time Range (HH:MM-HH:MM)
            time_range_str = parts[0]
            time_match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", time_range_str)
            if not time_match:
                logger.warning(f"Skipping invalid time window definition (invalid time format '{time_range_str}'): '{window_def}'")
                continue
            start_h, start_m, end_h, end_m = map(int, time_match.groups())

            # Basic validation for hours/minutes
            if not (0 <= start_h < 24 and 0 <= start_m < 60 and 0 <= end_h < 24 and 0 <= end_m < 60):
                 logger.warning(f"Skipping invalid time window definition (invalid hour/minute values): '{window_def}'")
                 continue

            # Store start/end as hour numbers (0-23) - simplify for now, ignore minutes
            # Handle midnight wrap around later if needed
            start_hour = start_h
            end_hour = end_h # Note: end hour is exclusive in range checks usually

            # Parse Criteria (moods=A,B;styles=C,D)
            criteria_str = parts[1] if len(parts) == 2 else parts[2] # Allow ':' in criteria values if split was 3 parts
            criteria = {'moods': [], 'styles': []} # Add more keys later if needed (e.g., tempo)
            crit_parts = criteria_str.split(';')
            for crit_part in crit_parts:
                if '=' not in crit_part: continue
                key, value_str = crit_part.split('=', 1)
                key = key.strip().lower()
                values = [v.strip() for v in value_str.split(',') if v.strip()]
                if key in criteria and values:
                    # Add values, converting case for consistency if desired
                    criteria[key].extend([v.capitalize() for v in values]) # Example: Capitalize moods/styles
                    logger.debug(f"Parsed criteria for window {i}: {key}={criteria[key]}")

            if not any(criteria.values()): # Check if any criteria were actually parsed
                logger.warning(f"Skipping time window definition (no valid criteria found): '{window_def}'")
                continue

            TIME_WINDOWS_CONFIG.append({
                'start_hour': start_hour,
                'end_hour': end_hour, # Exclusive
                'criteria': criteria
            })
            logger.debug(f"Added time window: Start={start_hour}, End={end_hour}, Criteria={criteria}")

        if not TIME_WINDOWS_CONFIG:
             logger.warning("ENABLE_TIME_PLAYLIST is true, but no valid TIME_WINDOWS definitions were parsed. Time playlist will not be generated.")
             # Optionally disable the feature flag here?
             # ENABLE_TIME_PLAYLIST = False
        else:
             logger.info(f"Successfully parsed {len(TIME_WINDOWS_CONFIG)} time window definitions.")

    elif ENABLE_TIME_PLAYLIST:
         logger.warning("ENABLE_TIME_PLAYLIST is true, but TIME_WINDOWS environment variable is empty or missing. Time playlist will not be generated.")
         # Optionally disable
         # ENABLE_TIME_PLAYLIST = False

    # Logging Level (Already handled in log_config)
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

    # --- Post-load Validation ---

    if (ENABLE_LASTFM_RECS or ENABLE_LASTFM_CHARTS) and (not LASTFM_API_KEY or not LASTFM_USER):
        logger.warning("Last.fm features enabled but LASTFM_API_KEY or LASTFM_USER is missing.")
        # Decide if this should be an error or just disable the features

    logger.info("Configuration loaded successfully.")
    if LOG_LEVEL == 'DEBUG':
        logger.debug(f"PLEX_URL: {PLEX_URL}")
        logger.debug(f"PLEX_MUSIC_LIBRARY_NAMES: {PLEX_MUSIC_LIBRARY_NAMES}")
        logger.debug(f"RUN_INTERVAL_MINUTES: {RUN_INTERVAL_MINUTES}")
        logger.debug(f"ENABLE_LASTFM_CHARTS: {ENABLE_LASTFM_CHARTS}")
        # Add other relevant non-sensitive vars here

except ValueError as e:
    logger.error(f"Configuration error: {e}")
    raise SystemExit(f"Configuration error: {e}")
except Exception as e:
    logger.exception(f"An unexpected error occurred during configuration loading: {e}")
    raise SystemExit(f"Unexpected configuration loading error: {e}")