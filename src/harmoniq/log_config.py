# src/harmoniq/log_config.py
import logging
import os
import sys

# This initial setup should ideally be minimal, as config.py will reconfigure.
_initial_log_level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
_initial_log_level = getattr(logging, _initial_log_level_name, logging.INFO)

# Keep basicConfig for now, config.py will override root logger level
logging.basicConfig(
    level=_initial_log_level, 
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger("Harmoniq") # Get the application's root logger instance

def apply_final_log_level(level_name_str):
    final_log_level_name = level_name_str.upper()
    final_log_level = getattr(logging, final_log_level_name, None)
    current_root_level = logging.getLogger().getEffectiveLevel()

    if final_log_level is not None:
        if current_root_level == final_log_level:
            logger.info(f"Root logger level already set to: {final_log_level_name}. No change needed.")
        else:
            root_logger = logging.getLogger()
            root_logger.setLevel(final_log_level)
            logger.info(f"Logging reconfigured. Root logger level set to: {logging.getLogger().getEffectiveLevel()} ({final_log_level_name}). Harmoniq logger effective level: {logger.getEffectiveLevel()}")
    else:
        logger.warning(f"Invalid LOG_LEVEL '{level_name_str}' provided for reconfiguration. Keeping current level: {logging.getLevelName(current_root_level)}")

# Log initial state immediately
logger.info(f"Initial logging configured by log_config. Harmoniq logger level: {logger.getEffectiveLevel()} (based on root: {logging.getLevelName(logging.getLogger().getEffectiveLevel())})")