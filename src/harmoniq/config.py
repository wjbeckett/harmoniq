# src/harmoniq/config.py
import os
import logging
import yaml 
from dotenv import load_dotenv
import re
import sys

# Initial load_dotenv() to get potential CONFIG_FILE_PATH from .env for YAML loading
load_dotenv() 

logger = logging.getLogger(__name__) 

# --- Default Vibe Definitions (Internal) ---
DEFAULT_PERIOD_VIBES = {
    "EarlyMorning": {"moods": ["Calm", "Peaceful", "Relaxed"], "styles": ["Ambient", "Acoustic", "Instrumental"]},
    "Morning": {"moods": ["Focused", "Energetic", "Upbeat"], "styles": ["Electronic", "Pop", "Rock"]},
    "Midday": {"moods": ["Upbeat", "Happy", "Energetic"], "styles": ["Pop", "Rock", "Indie"]},
    "Afternoon": {"moods": ["Energetic", "Rowdy", "Driving"], "styles": ["Rock", "Electronic", "Rap"]},
    "Evening": {"moods": ["Relaxed", "Cool", "Sentimental", "Romantic"], "styles": ["Jazz", "Blues", "Soul", "R&B"]},
    "LateNight": {"moods": ["Atmospheric", "Mellow", "Brooding", "Nocturnal"], "styles": ["Ambient", "Electronic", "Trip Hop", "Classical"]},
    "DefaultVibe": {"moods": ["Eclectic"], "styles": ["Mixed"]} 
}
DEFAULT_COVER_PERIOD_COLORS = { # Moved here for clarity
    "EarlyMorning": ((60, 70, 100), (100, 120, 160)), "Morning": ((100, 150, 200), (180, 210, 230)),
    "Midday": ((255, 200, 100), (255, 160, 80)), "Afternoon": ((255, 120, 80), (220, 80, 60)),
    "Evening": ((80, 60, 110), (140, 100, 160)), "LateNight": ((30, 30, 60), (70, 70, 100)),
    "DefaultVibe": ((100, 100, 100), (150, 150, 150))
}

# Wrap all configuration loading in a single try-except block at the module level
try:
    # --- Configuration Loading Logic ---
    ALL_CONFIG_DEFINITIONS = {
        "PLEX_URL": {"default": None, "type": str, "required": True, "yaml_path": "plex_url"},
        "PLEX_TOKEN": {"default": None, "type": str, "required": True, "yaml_path": "plex_token"},
        "PLEX_MUSIC_LIBRARY_NAMES": {"default": "Music", "type": list, "yaml_path": "plex_music_library_names"}, # Env var is comma-separated string
        "RUN_INTERVAL_MINUTES": {"default": 1440, "type": int},
        "TIMEZONE": {"default": "UTC", "type": str, "yaml_path": "timezone"},
        "LASTFM_API_KEY": {"default": None, "type": str, "yaml_path": "lastfm_api_key"},
        "LASTFM_USER": {"default": None, "type": str, "yaml_path": "lastfm_user"},

        "ENABLE_TIME_PLAYLIST": {"default": True, "type": bool, "yaml_path": "features.enable_time_playlist"},
        "ENABLE_LASTFM_RECS": {"default": True, "type": bool, "yaml_path": "features.enable_lastfm_recs"},
        "ENABLE_LASTFM_CHARTS": {"default": True, "type": bool, "yaml_path": "features.enable_lastfm_charts"},
        "ENABLE_PLAYLIST_COVERS": {"default": True, "type": bool, "yaml_path": "features.enable_playlist_covers"},

        "TIME_PLAYLIST_LEARN_FROM_HISTORY": {"default": True, "type": bool, "yaml_path": "features.time_playlist.learn_from_history"},
        "TIME_PLAYLIST_INCLUDE_HISTORY_TRACKS": {"default": True, "type": bool, "yaml_path": "features.time_playlist.include_history_tracks"},
        "TIME_PLAYLIST_USE_SONIC_EXPANSION": {"default": True, "type": bool, "yaml_path": "features.time_playlist.use_sonic_expansion"},
        "TIME_PLAYLIST_USE_SONIC_ADVENTURE": {"default": False, "type": bool, "yaml_path": "features.time_playlist.use_sonic_adventure"},
        "TIME_PLAYLIST_SONIC_SORT": {"default": True, "type": bool, "yaml_path": "features.time_playlist.sonic_sort"},

        "PLAYLIST_NAME_TIME": {"default": "Harmoniq Flow", "type": str, "yaml_path": "playlists.time_flow.name"},
        "PLAYLIST_SIZE_TIME": {"default": 50, "type": int, "yaml_path": "playlists.time_flow.size"},
        "TIME_PLAYLIST_MIN_RATING": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.min_rating"},
        "TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS": {"default": 21, "type": int, "yaml_path": "playlists.time_flow.exclude_played_days"},
        "TIME_PLAYLIST_MAX_SKIP_COUNT": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.max_skip_count"},
        "TIME_PLAYLIST_HISTORY_LOOKBACK_DAYS": {"default": 90, "type": int, "yaml_path": "playlists.time_flow.history_lookback_days"},
        "TIME_PLAYLIST_HISTORY_MIN_PLAYS": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.history_min_plays"},
        "TIME_PLAYLIST_HISTORY_MIN_RATING": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.history_min_rating"},
        "TIME_PLAYLIST_TARGET_HISTORY_COUNT": {"default": 7, "type": int, "yaml_path": "playlists.time_flow.target_history_count"},
        "TIME_PLAYLIST_VIBE_ANCHOR_COUNT": {"default": 5, "type": int, "yaml_path": "playlists.time_flow.vibe_anchor_count"},
        "TIME_PLAYLIST_SONIC_SEED_TRACKS": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.sonic_seed_tracks"},
        "TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED": {"default": 5, "type": int, "yaml_path": "playlists.time_flow.similar_tracks_per_seed"},
        "TIME_PLAYLIST_SONIC_MAX_DISTANCE": {"default": 0.45, "type": float, "yaml_path": "playlists.time_flow.sonic_max_distance"},
        "TIME_PLAYLIST_FINAL_MIX_RATIO": {"default": 0.4, "type": float, "yaml_path": "playlists.time_flow.final_mix_ratio"},
        "TIME_PLAYLIST_SONIC_SORT_SIMILARITY_LIMIT": {"default": 20, "type": int, "yaml_path": "playlists.time_flow.sonic_sort_similarity_limit"},
        "TIME_PLAYLIST_SONIC_SORT_MAX_DISTANCE": {"default": 0.65, "type": float, "yaml_path": "playlists.time_flow.sonic_sort_max_distance"},
        
        "TIME_PLAYLIST_LEARNED_VIBE_LOOKBACK_DAYS": {"default": 60, "type": int, "yaml_path": "playlists.time_flow.learned_vibe.lookback_days"},
        "TIME_PLAYLIST_LEARNED_VIBE_TOP_N_MOODS": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.learned_vibe.top_n_moods"},
        "TIME_PLAYLIST_LEARNED_VIBE_TOP_M_STYLES": {"default": 3, "type": int, "yaml_path": "playlists.time_flow.learned_vibe.top_m_styles"},
        "TIME_PLAYLIST_LEARNED_VIBE_MIN_OCCURRENCES": {"default": 2, "type": int, "yaml_path": "playlists.time_flow.learned_vibe.min_occurrences"},

        "PLAYLIST_NAME_LASTFM_RECS": {"default": "Last.fm Discovery", "type": str, "yaml_path": "playlists.lastfm_recs.name"},
        "PLAYLIST_SIZE_LASTFM_RECS": {"default": 30, "type": int, "yaml_path": "playlists.lastfm_recs.size"},
        "PLAYLIST_NAME_LASTFM_CHARTS": {"default": "Last.fm Global Charts", "type": str, "yaml_path": "playlists.lastfm_charts.name"},
        "PLAYLIST_SIZE_LASTFM_CHARTS": {"default": 50, "type": int, "yaml_path": "playlists.lastfm_charts.size"},
        
        "COVER_FONT_FILE_PATH": {"default": "/app/harmoniq/fonts/DejaVuSans-Bold.ttf", "type": str, "yaml_path": "cover_settings.font_file_path"},
        "COVER_OUTPUT_PATH": {"default": "/tmp/harmoniq_cover.png", "type": str, "yaml_path": "cover_settings.output_path"},
        "CONFIG_FILE_PATH": {"default": "/app/config/config.yaml", "type": str},
        "LOG_LEVEL": {"default": "INFO", "type": str, "yaml_path": "log_level"},
        "TIME_PERIOD_SCHEDULE_RAW_ENV": {"default": "Morning=7;Midday=12;Afternoon=16;Evening=19;LateNight=22", "type": str, "env_only": True}
    }

    _CONFIG_FILE_PATH = os.environ.get("CONFIG_FILE_PATH", ALL_CONFIG_DEFINITIONS["CONFIG_FILE_PATH"]["default"])
    yaml_config_data = {}
    if os.path.exists(_CONFIG_FILE_PATH):
        try:
            with open(_CONFIG_FILE_PATH, 'r') as f: yaml_config_data = yaml.safe_load(f) or {}
            logger.info(f"Successfully loaded configuration from YAML file: {_CONFIG_FILE_PATH}")
        except yaml.YAMLError as e: logger.error(f"Error parsing YAML config at {_CONFIG_FILE_PATH}: {e}.")
        except IOError as e: logger.warning(f"Could not read YAML config at {_CONFIG_FILE_PATH}: {e}.")
    else: logger.info(f"No YAML config file found at {_CONFIG_FILE_PATH}. Using defaults and environment variables.")

    def _get_nested_val(data_dict, path_str, default=None):
        keys = path_str.split('.'); val = data_dict
        try:
            for key_part in keys: val = val[key_part]
            return val
        except (KeyError, TypeError): return default

    def _get_config_value(env_key, definition, yaml_data):
        val_type = definition["type"]; default_val = definition["default"]
        env_val = os.environ.get(env_key)
        if env_val is not None:
            logger.debug(f"Loading '{env_key}' from ENV ('{env_val}').")
            if val_type == bool: return env_val.lower() in ['true', '1', 'yes']
            if val_type == list: return [item.strip() for item in env_val.split(',') if item.strip()]
            try: return val_type(env_val)
            except ValueError: logger.error(f"Invalid ENV type for {env_key}. Defaulting."); return default_val
        yaml_path = definition.get("yaml_path")
        if yaml_path and yaml_data:
            yaml_val = _get_nested_val(yaml_data, yaml_path)
            if yaml_val is not None:
                logger.debug(f"Loading '{env_key}' from YAML '{yaml_path}' ('{yaml_val}').")
                if val_type == bool: return bool(yaml_val)
                if val_type == list: return yaml_val if isinstance(yaml_val, list) else default_val
                try: return val_type(yaml_val)
                except ValueError: logger.error(f"Invalid YAML type for {env_key} at {yaml_path}. Defaulting."); return default_val
        logger.debug(f"Loading '{env_key}' from default ('{default_val}')."); return default_val

    # Populate module-level variables using globals()
    # This ensures they are defined in the module scope for subsequent access
    # For required fields, if they end up as None after this process, validation will catch it.
    for key, definition in ALL_CONFIG_DEFINITIONS.items():
        if not definition.get("env_only"):
            globals()[key] = _get_config_value(key, definition, yaml_config_data)
            if definition.get("required") and globals()[key] is None:
                logger.error(f"CRITICAL: Required configuration '{key}' is missing.")
                raise ValueError(f"Required configuration '{key}' is missing.")
            
    final_log_level_str = globals().get("LOG_LEVEL", "INFO") # Get final LOG_LEVEL
    # Import and call the function to apply it
    from .log_config import apply_final_log_level as apply_log_level_from_config
    apply_log_level_from_config(final_log_level_str)
            
    logger.info(f"[CONFIG_PY_FINAL] TIMEZONE is set to: '{TIMEZONE}' (Type: {type(TIMEZONE)})")


    # --- Special Handling for COVER_PERIOD_COLORS ---
    COVER_PERIOD_COLORS = DEFAULT_COVER_PERIOD_COLORS.copy() 
    yaml_cover_settings_colors = _get_nested_val(yaml_config_data, "cover_settings.period_colors")
    if isinstance(yaml_cover_settings_colors, dict):
        logger.info("Loading COVER_PERIOD_COLORS from YAML 'cover_settings.period_colors'.")
        for period_name, color_values in yaml_cover_settings_colors.items():
            # ... (color parsing logic as before) ...
            if isinstance(color_values, list) and len(color_values) == 2:
                try:
                    c1_tuple, c2_tuple = None, None
                    if isinstance(color_values[0], str) and color_values[0].startswith("#"): c1_tuple = tuple(int(color_values[0].lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                    elif isinstance(color_values[0], list) and len(color_values[0]) == 3: c1_tuple = tuple(color_values[0])
                    if isinstance(color_values[1], str) and color_values[1].startswith("#"): c2_tuple = tuple(int(color_values[1].lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                    elif isinstance(color_values[1], list) and len(color_values[1]) == 3: c2_tuple = tuple(color_values[1])
                    if c1_tuple and c2_tuple and all(0<=c<=255 for c in c1_tuple) and all(0<=c<=255 for c in c2_tuple):
                        COVER_PERIOD_COLORS[period_name] = (c1_tuple, c2_tuple); logger.debug(f"Overriding cover colors for '{period_name}' from YAML: {COVER_PERIOD_COLORS[period_name]}")
                    else: logger.warning(f"Invalid color format for period '{period_name}' in YAML.")
                except Exception as e_color: logger.warning(f"Error parsing colors for '{period_name}' in YAML: {e_color}")
            else: logger.warning(f"Invalid format for period '{period_name}' in YAML 'cover_settings.period_colors'.")
    elif yaml_cover_settings_colors is not None: logger.warning("'cover_settings.period_colors' in YAML is not a dict.")

    # --- Special Handling for Time Period Schedule & Vibe Overrides ---
    SCHEDULED_PERIODS = []
    
    if globals().get("ENABLE_TIME_PLAYLIST"):
        yaml_time_periods = yaml_config_data.get("time_periods") if isinstance(yaml_config_data.get("time_periods"), list) else []
        parsed_from_yaml = False
        if yaml_time_periods:
            logger.info("Parsing 'time_periods' from YAML configuration...")
            temp_periods_yaml = {}
            for entry in yaml_time_periods: # Iterate through list of dicts
                if isinstance(entry, dict) and 'name' in entry and 'start_hour' in entry:
                    name, hour = entry['name'], entry['start_hour']
                    crit_yaml = entry.get('criteria', {})
                    yaml_m = crit_yaml.get('moods', [])
                    yaml_s = crit_yaml.get('styles', [])
                    default_vibe = DEFAULT_PERIOD_VIBES.get(name, DEFAULT_PERIOD_VIBES["DefaultVibe"])
                    moods = [m.strip().capitalize() for m in yaml_m if m] or default_vibe['moods']
                    styles = [s.strip().capitalize() for s in yaml_s if s] or default_vibe['styles']
                    if name not in temp_periods_yaml: temp_periods_yaml[name] = {'hour': hour, 'moods': moods, 'styles': styles}
                    else: logger.warning(f"Duplicate YAML period name '{name}'. Ignoring subsequent.")
            if temp_periods_yaml:
                sorted_names = sorted(temp_periods_yaml.keys(), key=lambda k: temp_periods_yaml[k]['hour'])
                for name_s in sorted_names:
                    SCHEDULED_PERIODS.append({'name': name_s, 'start_hour': temp_periods_yaml[name_s]['hour'], 'criteria': {'moods': temp_periods_yaml[name_s]['moods'], 'styles': temp_periods_yaml[name_s]['styles']}})
                if SCHEDULED_PERIODS: parsed_from_yaml = True; logger.info(f"Loaded {len(SCHEDULED_PERIODS)} periods from YAML.")

        if not parsed_from_yaml and globals().get("TIME_PERIOD_SCHEDULE_RAW_ENV"):
            logger.info(f"No periods from YAML or YAML not used. Parsing TIME_PERIOD_SCHEDULE_RAW_ENV: '{globals()['TIME_PERIOD_SCHEDULE_RAW_ENV']}'")
            period_defs_env = [p.strip() for p in globals()['TIME_PERIOD_SCHEDULE_RAW_ENV'].strip().split(';') if p.strip()]
            temp_periods_env = {}
            for p_def in period_defs_env: # Existing ENV parsing logic
                if '=' not in p_def: continue
                name, hour_str = p_def.split('=', 1); name = name.strip()
                try:
                    hour = int(hour_str.strip()); # ... validation ...
                    user_moods_raw_env = os.environ.get(f"TP_DEFINE_{name.upper()}_MOODS", "")
                    user_styles_raw_env = os.environ.get(f"TP_DEFINE_{name.upper()}_STYLES", "")
                    default_vibe_env = DEFAULT_PERIOD_VIBES.get(name, DEFAULT_PERIOD_VIBES["DefaultVibe"])
                    moods_env = [m.strip().capitalize() for m in user_moods_raw_env.split(',') if m.strip()] if user_moods_raw_env else default_vibe_env['moods']
                    styles_env = [s.strip().capitalize() for s in user_styles_raw_env.split(',') if s.strip()] if user_styles_raw_env else default_vibe_env['styles']
                    if name not in temp_periods_env : temp_periods_env[name] = {'hour': hour, 'moods': moods_env, 'styles': styles_env}
                except ValueError: pass # Logged by get_env_var or earlier
            if temp_periods_env:
                sorted_names_env = sorted(temp_periods_env.keys(), key=lambda k: temp_periods_env[k]['hour'])
                for name_s_env in sorted_names_env:
                    SCHEDULED_PERIODS.append({'name': name_s_env, 'start_hour': temp_periods_env[name_s_env]['hour'], 'criteria': {'moods': temp_periods_env[name_s_env]['moods'], 'styles': temp_periods_env[name_s_env]['styles']}})
                logger.info(f"Loaded {len(SCHEDULED_PERIODS)} periods from ENV.")
        
        if not SCHEDULED_PERIODS: logger.warning("Harmoniq Flow enabled, but no valid periods parsed from YAML or ENV.")
        # else: logger.info(f"Successfully configured {len(SCHEDULED_PERIODS)} time periods for Harmoniq Flow.") # Logged per source


    # --- Final Validations (using globals().get() for safety) ---
    if not globals().get("PLEX_URL") or not globals().get("PLEX_TOKEN"):
        critical_error_msg = "CRITICAL FAILURE: PLEX_URL or PLEX_TOKEN not configured after loading all sources."
        logger.error(critical_error_msg)
        raise ValueError(critical_error_msg)
    
    if globals().get("ENABLE_LASTFM_RECS") or globals().get("ENABLE_LASTFM_CHARTS"):
        if not globals().get("LASTFM_API_KEY") or not globals().get("LASTFM_USER"):
            logger.warning("Last.fm features enabled but API Key/User missing. These features will be skipped.")
            globals()["ENABLE_LASTFM_RECS"] = False # Disable if misconfigured
            globals()["ENABLE_LASTFM_CHARTS"] = False

    if globals().get("TIME_PLAYLIST_USE_SONIC_EXPANSION"):
        mix_ratio = globals().get("TIME_PLAYLIST_FINAL_MIX_RATIO", 0.5)
        if not (0.0 <= mix_ratio <= 1.0):
            logger.warning("TIME_PLAYLIST_FINAL_MIX_RATIO must be between 0.0 and 1.0. Defaulting to 0.5")
            globals()["TIME_PLAYLIST_FINAL_MIX_RATIO"] = 0.5
        if globals().get("TIME_PLAYLIST_SONIC_SEED_TRACKS", 0) <= 0:
            logger.warning("TIME_PLAYLIST_SONIC_SEED_TRACKS must be positive. Disabling sonic expansion.")
            globals()["TIME_PLAYLIST_USE_SONIC_EXPANSION"] = False
        if globals().get("TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED", 0) <= 0:
            logger.warning("TIME_PLAYLIST_SIMILAR_TRACKS_PER_SEED must be positive. Disabling sonic expansion.")
            globals()["TIME_PLAYLIST_USE_SONIC_EXPANSION"] = False

    if globals().get("TIME_PLAYLIST_LEARN_FROM_HISTORY", False):
        if globals().get("TIME_PLAYLIST_LEARNED_VIBE_LOOKBACK_DAYS", 0) <= 0:
            logger.warning("TIME_PLAYLIST_LEARNED_VIBE_LOOKBACK_DAYS must be positive. Disabling vibe learning.")
            globals()["TIME_PLAYLIST_LEARN_FROM_HISTORY"] = False
        # Add similar checks for TOP_N_MOODS, TOP_M_STYLES, MIN_OCCURRENCES if they can break logic

    if globals().get("ENABLE_PLAYLIST_COVERS"):
        font_path = globals().get("COVER_FONT_FILE_PATH")
        # Check for the default font path only if it's the one set (to avoid warning for user-set paths)
        if font_path == ALL_CONFIG_DEFINITIONS["COVER_FONT_FILE_PATH"]["default"] and not os.path.exists(font_path):
            logger.warning(f"Playlist covers enabled, but default font at '{font_path}' might not exist. Consider bundling a font or setting COVER_FONT_FILE_PATH in config.yaml or ENV.")

    logger.info("Global configuration variables populated and validated (YAML + ENV).")

except ValueError as e_config: 
    logger.critical(f"CRITICAL CONFIGURATION ERROR (ValueError): {e_config}")
    raise SystemExit(f"Configuration error: {e_config}")
except Exception as e_unexpected_config: 
    logger.critical(f"CRITICAL UNEXPECTED CONFIGURATION ERROR: {e_unexpected_config}", exc_info=True)
    raise SystemExit(f"Unexpected critical configuration loading error: {e_unexpected_config}")

# --- Import and apply final log level AFTER all config is set ---
from .log_config import apply_final_log_level, logger as harmoniq_app_logger

final_log_level_to_apply = str(globals().get("LOG_LEVEL", "INFO")) # Ensure it's a string
apply_final_log_level(final_log_level_to_apply)

# Update this module's logger if needed, though root change should propagate
# logger.setLevel(logging.getLogger("Harmoniq").getEffectiveLevel()) # Harmoniq app logger, not config's logger
logger.info(f"harmoniq.config logger effective level now: {logger.getEffectiveLevel()}")