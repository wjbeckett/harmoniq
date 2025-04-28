import logging

# Import config variables (they are loaded when config.py is imported)
from . import config

# Import logger configured in log_config
from .log_config import logger


def run_playlist_update_cycle():
    """
    Placeholder for the main logic that fetches data and updates playlists.
    In Phase 1, this will run once. In Phase 2, it will be called by the scheduler.
    """
    logger.info("Starting playlist update cycle...")

    # --- Phase 1: Basic Structure ---
    logger.info(f"Plex URL: {config.PLEX_URL}")  # Log config loaded
    logger.info(f"Last.fm User: {config.LASTFM_USER}")  # Example

    # --- TODO: Implement Phase 1 Logic ---
    # 1. Connect to Plex
    # 2. If config.ENABLE_LASTFM_RECS:
    #    a. Fetch Last.fm recommendations
    #    b. Match tracks in Plex library
    #    c. Update/Create Plex playlist (config.PLAYLIST_NAME_LASTFM_RECS)

    logger.warning("Placeholder: Actual playlist generation not yet implemented.")

    logger.info("Playlist update cycle finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Phase 1 - Single Run)...")
    try:
        run_playlist_update_cycle()
    except Exception as e:
        logger.exception(f"An unexpected error occurred during the update cycle: {e}")
        # In Phase 1, the script will exit. In Phase 2, the scheduler loop should handle this.
    logger.info("Harmoniq service finished.")
