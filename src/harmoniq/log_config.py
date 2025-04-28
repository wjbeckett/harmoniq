import logging
import os
import sys


def setup_logging():
    """Configures logging based on LOG_LEVEL environment variable."""
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Basic configuration for logging to stdout
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout,  # Explicitly direct to stdout
    )

    # Silence overly verbose libraries if needed
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logger = logging.getLogger("Harmoniq")
    logger.info(f"Logging configured with level {log_level_name}")
    return logger


# Initialize logger when module is imported
logger = setup_logging()
