# src/harmoniq/config.py
import os
import logging
from dotenv import load_dotenv
import re

load_dotenv()
logger = logging.getLogger(__name__)

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

DEFAULT_PERIOD_VIBES = {
    "EarlyMorning": {"moods": ["Calm", "Peaceful", "Relaxed"], "styles": ["Ambient", "Acoustic", "Instrumental"]},
    "Morning": {"moods": ["Focused", "Energetic", "Upbeat"], "styles": ["Electronic", "Pop", "Rock"]},
    "Midday": {"moods": ["Upbeat", "Happy", "Energetic"], "styles": ["Pop", "Rock", "Indie"]},
    "Afternoon": {"moods": ["Energetic", "Rowdy", "Driving"], "styles": ["Rock", "Electronic", "Rap"]},
    "Evening": {"moods": ["Relaxed", "Cool", "Sentimental", "Romantic"], "styles": ["Jazz", "Blues", "Soul", "R&B"]},
    "LateNight": {"moods": ["Atmospheric", "Mellow", "Brooding", "Nocturnal"], "styles": ["Ambient", "Electronic", "Trip Hop", "Classical"]},
    "DefaultVibe": {"moods": ["Eclectic"], "styles": ["Mixed"]}
}


# --- Load Configuration Settings ---
try:
    # Plex, Last.fm (as before)
    PLEX_URL = get_env_var("PLEX_URL", required=True)
    PLEX_TOKEN = get_env_var("PLEX_TOKEN", required=True)
    PLEX_MUSIC_LIBRARY_NAMES = get_env_var("PLEX_MUSIC_LIBRARY_NAMES", default="Music", required=True, var_type=list)
    RUN_INTERVAL_MINUTES = get_env_var("RUN_INTERVAL_MINUTES", default=1440, var_type=int) # For Last.fm
    TIMEZONE = get_env_var("TIMEZONE", default="UTC")
    LASTFM_API_KEY = get_env_var("LASTFM_API_KEY")
    LASTFM_USER = get_env_var("LASTFM_USER")

    # Feature Flags
    ENABLE_LASTFM_RECS = get_env_var("ENABLE_LASTFM_RECS", default=True, var_type=bool)
    ENABLE_LASTFM_CHARTS = get_env_var("ENABLE_LASTFM_CHARTS", default=True, var_type=bool)
    ENABLE_TIME_PLAYLIST = get_env_var("ENABLE_TIME_PLAYLIST", default=True, var_type=bool) # "Daily Flow" is now "Vibe Adventure"

    # Playlist Naming & Sizing (as before)
    PLAYLIST_NAME_LASTFM_RECS = get_env_var("PLAYLIST_NAME_LASTFM_RECS", "Last.fm Discovery")
    PLAYLIST_NAME_LASTFM_CHARTS = get_env_var("PLAYLIST_NAME_LASTFM_CHARTS", "Last.fm Global Charts")
    PLAYLIST_NAME_TIME = get_env_var("PLAYLIST_NAME_TIME", "Harmoniq Flow") # New name
    PLAYLIST_SIZE_LASTFM_RECS = get_env_var("PLAYLIST_SIZE_LASTFM_RECS", 30, var_type=int)
    PLAYLIST_SIZE_LASTFM_CHARTS = get_env_var("PLAYLIST_SIZE_LASTFM_CHARTS", 50, var_type=int)
    PLAYLIST_SIZE_TIME = get_env_var("PLAYLIST_SIZE_TIME", 40, var_type=int)

    # Time Period Schedule & Vibe Overrides
    TIME_PERIOD_SCHEDULE_RAW = get_env_var("TIME_PERIOD_SCHEDULE", default="Morning=7;Midday=12;Afternoon=16;Evening=19;LateNight=22")
    # Parsed structure: [{'name': 'Morning', 'start_hour': 7, 'moods': [...], 'styles': [...]}, ...]
    SCHEDULED_PERIODS = []

    if ENABLE_TIME_PLAYLIST and TIME_PERIOD_SCHEDULE_RAW:
        logger.info(f"Parsing TIME_PERIOD_SCHEDULE: '{TIME_PERIOD_SCHEDULE_RAW}'")
        period_defs = [p.strip() for p in TIME_PERIOD_SCHEDULE_RAW.strip().split(';') if p.strip()]
        temp_periods = {} # Temp dict to store name:hour for sorting
        for p_def in period_defs:
            if '=' not in p_def: logger.warning(f"Invalid period definition (missing '='): '{p_def}'. Skipping."); continue
            name, hour_str = p_def.split('=', 1)
            name = name.strip()
            try:
                hour = int(hour_str.strip())
                if not (0 <= hour < 24): logger.warning(f"Invalid hour '{hour}' for period '{name}'. Skipping."); continue
                if not name: logger.warning(f"Period name cannot be empty for hour '{hour}'. Skipping."); continue
                if name in temp_periods: logger.warning(f"Duplicate period name '{name}'. Using first definition."); continue
                temp_periods[name] = hour
            except ValueError: logger.warning(f"Invalid hour format '{hour_str}' for period '{name}'. Skipping.")

        # Sort periods by start hour to determine window boundaries
        if temp_periods:
            sorted_period_names_by_hour = sorted(temp_periods.keys(), key=lambda k: temp_periods[k])
            
            for i, period_name in enumerate(sorted_period_names_by_hour):
                start_hour = temp_periods[period_name]
                
                # Determine end_hour (start of next period, or wraps around)
                # This logic needs to be smarter for scheduler; scheduler just needs start times.
                # For GETTING criteria, we need to know which period is *currently active*.

                # Get user-defined vibe overrides for this period
                user_moods_raw = get_env_var(f"TP_DEFINE_{period_name.upper()}_MOODS", default="")
                user_styles_raw = get_env_var(f"TP_DEFINE_{period_name.upper()}_STYLES", default="")

                final_moods = [m.strip().capitalize() for m in user_moods_raw.split(',') if m.strip()] if user_moods_raw else DEFAULT_PERIOD_VIBES.get(period_name, DEFAULT_PERIOD_VIBES["DefaultVibe"])['moods']
                final_styles = [s.strip().capitalize() for s in user_styles_raw.split(',') if s.strip()] if user_styles_raw else DEFAULT_PERIOD_VIBES.get(period_name, DEFAULT_PERIOD_VIBES["DefaultVibe"])['styles']
                
                SCHEDULED_PERIODS.append({
                    'name': period_name,
                    'start_hour': start_hour,
                    'criteria': {'moods': final_moods, 'styles': final_styles}
                })
                logger.info(f"Scheduled period '{period_name}' starting at {start_hour:02d}:00 with Moods: {final_moods}, Styles: {final_styles}")
        
        if not SCHEDULED_PERIODS: logger.warning("No valid periods parsed from TIME_PERIOD_SCHEDULE.")
        else: logger.info(f"Successfully configured {len(SCHEDULED_PERIODS)} time periods for Harmoniq Flow.")

    elif ENABLE_TIME_PLAYLIST: logger.warning("Harmoniq Flow enabled, but TIME_PERIOD_SCHEDULE is empty.")

    # Time Playlist Refinements
    TIME_PLAYLIST_MIN_RATING = get_env_var("TIME_PLAYLIST_MIN_RATING", default=0, var_type=int)
    TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS = get_env_var("TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS", default=0, var_type=int)
    TIME_PLAYLIST_MAX_SKIP_COUNT = get_env_var("TIME_PLAYLIST_MAX_SKIP_COUNT", default=999, var_type=int)

    # Sonic Expansion & Sort
    TIME_PLAYLIST_USE_SONIC_EXPANSION = get_env_var("TIME_PLAYLIST_USE_SONIC_EXPANSION", default=True, var_type=bool)
    TIME_PLAYLIST_SONIC_SEED_TRACKS = get_env_var("TIME_PLAYLIST_SONIC_SEED_TRACKS", default=3, var_type=int)
    TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED = get_env_var("TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED", default=5, var_type=int)
    TIME_PLAYLIST_SONIC_MAX_DISTANCE = get_env_var("TIME_PLAYLIST_SONIC_MAX_DISTANCE", default=0.4, var_type=float)
    TIME_PLAYLIST_FINAL_MIX_RATIO = get_env_var("TIME_PLAYLIST_FINAL_MIX_RATIO", default=0.5, var_type=float)
    TIME_PLAYLIST_SONIC_SORT = get_env_var("TIME_PLAYLIST_SONIC_SORT", default=True, var_type=bool)
    TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT = get_env_var("TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT", default=20, var_type=int)
    TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE = get_env_var("TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE", default=0.6, var_type=float)

    # History Integration Config
    TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS = get_env_var("TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS", default=True, var_type=bool)
    TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS = get_env_var("TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS", default=90, var_type=int)
    TIME_PLAYLIST_HISTORY_MIN_PLAYS = get_env_var("TIME_PLAYLIST_HISTORY_MIN_PLAYS", default=3, var_type=int)
    TIME_PLAYLIST_HISTORY_MIN_RATING = get_env_var("TIME_PLAYLIST_HISTORY_MIN_RATING", default=0, var_type=int)
    TIME_PLAYLIST_TARGET_HISTORY_COUNT = get_env_var("TIME_PLAYLIST_TARGET_HISTORY_COUNT", default=5, var_type=int)
    
    # Vibe Adventure (Sonic Adventure specific)
    TIME_PLAYLIST_VIBE_ANCHOR_COUNT = get_env_var("TIME_PLAYLIST_VIBE_ANCHOR_COUNT", default=3, var_type=int)
    TIME_PLAYLIST_USE_SONIC_ADVENTURE = get_env_var("TIME_PLAYLIST_USE_SONIC_ADVENTURE", default=False, var_type=bool)

    # Learned Vibe Augmentation Configuration
    TIME_PLAYLIST_LEARN_FROM_HISTORY = get_env_var("TIME_PLAYLIST_LEARN_FROM_HISTORY", default=True, var_type=bool)
    TIME_PLAYLIST_LEARNED_VIBE_LOOKBACK_DAYS = get_env_var("TIME_PLAYLIST_LEARNED_VIBE_LOOKBACK_DAYS", default=60, var_type=int)
    TIME_PLAYLIST_LEARNED_VIBE_TOP_N_MOODS = get_env_var("TIME_PLAYLIST_LEARNED_VIBE_TOP_N_MOODS", default=3, var_type=int)
    TIME_PLAYLIST_LEARNED_VIBE_TOP_M_STYLES = get_env_var("TIME_PLAYLIST_LEARNED_VIBE_TOP_M_STYLES", default=3, var_type=int)
    TIME_PLAYLIST_LEARNED_VIBE_MIN_OCCURRENCES = get_env_var("TIME_PLAYLIST_LEARNED_VIBE_MIN_OCCURRENCES", default=2, var_type=int)

    # Playlist Cover Generation Configuration
    ENABLE_PLAYLIST_COVERS = get_env_var("ENABLE_PLAYLIST_COVERS", default=True, var_type=bool)
    # Font path within the container. We'll need to add a font file.
    # Default to a common system font path as a fallback, but ideally user provides one via volume mount or we bundle one.
    # For now, let's assume we'll bundle one.
    COVER_FONT_FILE_PATH = get_env_var("COVER_FONT_FILE_PATH", default="/app/harmoniq/fonts/DejaVuSans-Bold.ttf") # Example path
    COVER_OUTPUT_PATH = get_env_var("COVER_OUTPUT_PATH", default="/tmp/harmoniq_cover.png") # Temporary path for generated image
    # Define base colors for periods (can be expanded) - RGB tuples
    # These are just examples, can be made more sophisticated
    COVER_PERIOD_COLORS = {
        "EarlyMorning": ((60, 70, 100), (100, 120, 160)), # Dark blues / purples
        "Morning": ((100, 150, 200), (180, 210, 230)),   # Lighter blues / Sky
        "Midday": ((255, 200, 100), (255, 160, 80)),     # Oranges / Yellows
        "Afternoon": ((255, 120, 80), (220, 80, 60)),    # Reds / Oranges
        "Evening": ((80, 60, 110), (140, 100, 160)),     # Purples / Dark Blues
        "LateNight": ((30, 30, 60), (70, 70, 100)),       # Very Dark Blues / Indigos
        "DefaultVibe": ((100, 100, 100), (150, 150, 150)) # Greys
    }
    # Allow user to override these via a structured env var if desired later, e.g.,
    # COVER_COLOR_OVERRIDES="Morning=#RRGGBB,#RRGGBB;Evening=#RRGGBB,#RRGGBB"
    # For now, use internal defaults.

    # Logging Level
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

    # --- Post-load Validation ---
    if (ENABLE_LASTFM_RECS or ENABLE_LASTFM_CHARTS) and (not LASTFM_API_KEY or not LASTFM_USER):
        logger.warning("Last.fm features enabled but API Key/User missing. These features will be skipped.")
    
    if TIME_PLAYLIST_USE_SONIC_EXPANSION:
        if not (0.0 <= TIME_PLAYLIST_FINAL_MIX_RATIO <= 1.0):
            logger.warning("TIME_PLAYLIST_FINAL_MIX_RATIO must be between 0.0 and 1.0. Defaulting to 0.5")
            TIME_PLAYLIST_FINAL_MIX_RATIO = 0.5
        if TIME_PLAYLIST_SONIC_SEED_TRACKS <= 0:
            logger.warning("TIME_PLAYLIST_SONIC_SEED_TRACKS must be positive. Disabling sonic expansion.")
            TIME_PLAYLIST_USE_SONIC_EXPANSION = False
        if TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED <= 0:
            logger.warning("TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED must be positive. Disabling sonic expansion.")
            TIME_PLAYLIST_USE_SONIC_EXPANSION = False

    if TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS:
        if TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS <= 0:
            logger.warning("TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS must be positive. Disabling history track inclusion.")
            TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS = False
        if TIME_PLAYLIST_TARGET_HISTORY_COUNT <=0:
            logger.warning("TIME_PLAYLIST_TARGET_HISTORY_COUNT must be positive. Setting to 1 if history inclusion is enabled.")
            if TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS: TIME_PLAYLIST_TARGET_HISTORY_COUNT = 1 # Ensure at least 1 if enabled
            else: TIME_PLAYLIST_TARGET_HISTORY_COUNT = 0

    if ENABLE_PLAYLIST_COVERS and not os.path.exists(COVER_FONT_FILE_PATH) and COVER_FONT_FILE_PATH == "/app/harmoniq/fonts/DejaVuSans-Bold.ttf":
        logger.warning(f"Playlist covers enabled, but default font at '{COVER_FONT_FILE_PATH}' might not exist. Consider bundling a font or setting COVER_FONT_FILE_PATH.")

    logger.info("Configuration loaded successfully.")

except ValueError as e: logger.error(f"Configuration error: {e}"); raise SystemExit(f"Configuration error: {e}")
except Exception as e: logger.exception(f"Unexpected error during configuration loading: {e}"); raise SystemExit(f"Unexpected configuration loading error: {e}")