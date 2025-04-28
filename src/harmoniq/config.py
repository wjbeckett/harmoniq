import os
import logging
from dotenv import load_dotenv

# Load .env file if it exists (primarily for local development)
load_dotenv()

logger = logging.getLogger(__name__)  # Use the logger configured in log_config


# Helper function to get environment variables
def get_env_var(var_name, default=None, required=False, var_type=str):
    value = os.environ.get(var_name, default)
    if required and value is None:
        logger.error(f"Missing required environment variable: {var_name}")
        raise ValueError(f"Missing required environment variable: {var_name}")
    if value is not None:
        try:
            if var_type == bool:
                # Handle boolean conversion robustly ('true', '1', 'yes' vs 'false', '0', 'no')
                if isinstance(value, str):
                    return value.lower() in ["true", "1", "yes"]
                return bool(value)  # Fallback for non-string bools?
            return var_type(value)
        except ValueError:
            logger.error(
                f"Invalid type for environment variable: {var_name}. Expected {var_type}, got '{value}'"
            )
            raise ValueError(f"Invalid type for environment variable: {var_name}")
    return default  # Return None or the default if not required and not set, or already correct type


# --- Load Configuration Settings ---
try:
    # Plex
    PLEX_URL = get_env_var("PLEX_URL", required=True)
    PLEX_TOKEN = get_env_var("PLEX_TOKEN", required=True)
    PLEX_MUSIC_LIBRARY_NAME = get_env_var(
        "PLEX_MUSIC_LIBRARY_NAME", default="Music", required=True
    )

    # Scheduling & Timezone
    RUN_INTERVAL_MINUTES = get_env_var(
        "RUN_INTERVAL_MINUTES", default=1440, var_type=int
    )
    TIMEZONE = get_env_var("TIMEZONE", default="UTC")  # Keep as string for now

    # Last.fm (Required only if enabled)
    LASTFM_API_KEY = get_env_var("LASTFM_API_KEY")
    LASTFM_USER = get_env_var("LASTFM_USER")

    # ListenBrainz (Required only if enabled)
    LISTENBRAINZ_USER_TOKEN = get_env_var("LISTENBRAINZ_USER_TOKEN")

    # Feature Flags
    ENABLE_LASTFM_RECS = get_env_var("ENABLE_LASTFM_RECS", default=True, var_type=bool)
    ENABLE_LASTFM_CHARTS = get_env_var(
        "ENABLE_LASTFM_CHARTS", default=True, var_type=bool
    )
    ENABLE_LISTENBRAINZ_RECS = get_env_var(
        "ENABLE_LISTENBRAINZ_RECS", default=False, var_type=bool
    )
    ENABLE_TIME_PLAYLIST = get_env_var(
        "ENABLE_TIME_PLAYLIST", default=False, var_type=bool
    )
    # ENABLE_CUSTOM_1 = get_env_var("ENABLE_CUSTOM_1", default=False, var_type=bool)

    # Playlist Naming
    PLAYLIST_NAME_LASTFM_RECS = get_env_var(
        "PLAYLIST_NAME_LASTFM_RECS", "Last.fm Discovery"
    )
    PLAYLIST_NAME_LASTFM_CHARTS = get_env_var(
        "PLAYLIST_NAME_LASTFM_CHARTS", "Last.fm Global Charts"
    )
    PLAYLIST_NAME_LISTENBRAINZ_RECS = get_env_var(
        "PLAYLIST_NAME_LISTENBRAINZ_RECS", "ListenBrainz Discovery"
    )
    PLAYLIST_NAME_TIME = get_env_var("PLAYLIST_NAME_TIME", "Daily Flow")
    # PLAYLIST_NAME_CUSTOM_1 = get_env_var("PLAYLIST_NAME_CUSTOM_1", "My Custom Playlist")

    # Playlist Sizing
    PLAYLIST_SIZE_LASTFM_RECS = get_env_var(
        "PLAYLIST_SIZE_LASTFM_RECS", 30, var_type=int
    )
    PLAYLIST_SIZE_LASTFM_CHARTS = get_env_var(
        "PLAYLIST_SIZE_LASTFM_CHARTS", 50, var_type=int
    )
    PLAYLIST_SIZE_LISTENBRAINZ_RECS = get_env_var(
        "PLAYLIST_SIZE_LISTENBRAINZ_RECS", 30, var_type=int
    )
    PLAYLIST_SIZE_TIME = get_env_var("PLAYLIST_SIZE_TIME", 40, var_type=int)
    # PLAYLIST_SIZE_CUSTOM_1 = get_env_var("PLAYLIST_SIZE_CUSTOM_1", 25, var_type=int)

    # Time Playlist Config (Load later when implemented)
    # TIME_WINDOWS_RAW = get_env_var("TIME_WINDOWS")

    # Logging Level (Already handled in log_config, but could be exposed here if needed)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    # --- Post-load Validation ---
    if (ENABLE_LASTFM_RECS or ENABLE_LASTFM_CHARTS) and (
        not LASTFM_API_KEY or not LASTFM_USER
    ):
        logger.warning(
            "Last.fm features enabled but LASTFM_API_KEY or LASTFM_USER is missing."
        )
        # Depending on strictness, could raise error or just disable features

    if ENABLE_LISTENBRAINZ_RECS and not LISTENBRAINZ_USER_TOKEN:
        logger.warning(
            "ListenBrainz features enabled but LISTENBRAINZ_USER_TOKEN is missing."
        )
        # Handle similarly

    logger.info("Configuration loaded successfully.")
    if LOG_LEVEL == "DEBUG":
        # Be careful about logging sensitive info even at DEBUG
        logger.debug(f"PLEX_URL: {PLEX_URL}")
        logger.debug(f"PLEX_MUSIC_LIBRARY_NAME: {PLEX_MUSIC_LIBRARY_NAME}")
        logger.debug(f"RUN_INTERVAL_MINUTES: {RUN_INTERVAL_MINUTES}")
        logger.debug(f"LASTFM_USER: {LASTFM_USER}")
        logger.debug(f"ENABLE_LASTFM_RECS: {ENABLE_LASTFM_RECS}")
        # Add other relevant non-sensitive vars here

except ValueError as e:
    logger.error(f"Configuration error: {e}")
    # Exit or raise prevents the app from continuing with bad config
    raise SystemExit(f"Configuration error: {e}")
