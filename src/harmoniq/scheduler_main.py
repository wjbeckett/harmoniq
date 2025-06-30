#!/usr/bin/env python3
"""
Harmoniq Scheduler Main - Enhanced for Web Integration
Preserves all existing functionality while adding web UI support
"""

import schedule
import time
import signal
import logging
import asyncio

from .main import (
    run_harmoniq_flow_update,
    get_active_period_details,
)
from .discovery_library_grower import AlbumDiscoveryEngine
from .lidarr_client import LidarrClient
from .plex_client import PlexClient
from .lastfm_client import LastfmClient
from . import config
from .log_config import logger
from .stats_tracker import get_stats_tracker
from .library_sync_manager import LibrarySyncManager
from .database import HarmoniqDatabase


shutdown_event_triggered = False


def handle_shutdown_signal(signum, frame):
    global shutdown_event_triggered
    if not shutdown_event_triggered:
        logger.info(
            f"Shutdown signal ({signal.Signals(signum).name}) received. Finishing current jobs and shutting down..."
        )
        shutdown_event_triggered = True
        schedule.clear()
    else:
        logger.info("Multiple shutdown signals received.")


signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

plex_client_global = None
lastfm_client_global = None
valid_music_libraries_global = []
target_library_global = None
discovery_engine_global = None


def initialize_global_clients_and_libs():
    global plex_client_global, lastfm_client_global, valid_music_libraries_global, target_library_global, discovery_engine_global
    logger.info("Scheduler: Initializing global Plex and Last.fm clients...")
    valid_music_libraries_global = (
        []
    )  # Reset for re-initialization if ever called again

    try:
        # Initialize Plex client
        plex_client_global = PlexClient()

        if plex_client_global:
            for name in config.PLEX_MUSIC_LIBRARY_NAMES:
                lib = plex_client_global.get_music_library(name)
                if lib:
                    valid_music_libraries_global.append(lib)
            if valid_music_libraries_global:
                target_library_global = valid_music_libraries_global[0]
                logger.info(
                    f"Scheduler: Accessed {len(valid_music_libraries_global)} Plex libraries. Target: '{target_library_global.title}'."
                )
            else:
                logger.error(
                    "Scheduler: Could not access any valid Plex music libraries."
                )
        else:
            logger.error("Scheduler: Plex client failed to initialize.")

        # Initialize other clients and database
        stats_tracker = get_stats_tracker()

        # Create client instances (not classes!)
        lidarr_client = LidarrClient(
            base_url=config.LIDARR_URL, api_key=config.LIDARR_API_KEY
        )

        # Initialize database
        import os

        config_dir = os.path.dirname(config.CONFIG_FILE_PATH)
        database = HarmoniqDatabase(os.path.join(config_dir, "harmoniq.db"))

        # Create sync manager with actual instances
        sync_manager = LibrarySyncManager(plex_client_global, lidarr_client, database)

        # Perform initial sync
        logger.info("Scheduler: Performing initial library sync...")
        sync_result = sync_manager.startup_sync()

        if sync_result["success"]:
            logger.info(
                f"Scheduler: Sync completed - {sync_result.get('total_unique_albums', 0)} albums cached"
            )
            # Start background sync
            sync_manager.start_background_sync(interval_hours=6)
        else:
            logger.error(
                f"Scheduler: Sync failed - {sync_result.get('error', 'Unknown error')}"
            )

        # Create discovery engine with sync manager
        discovery_engine_global = AlbumDiscoveryEngine(
            config, stats_tracker, sync_manager=sync_manager
        )
        logger.info("Scheduler: Discovery engine initialized successfully.")

    except Exception as e:
        logger.exception(
            f"Scheduler: Critical error during global client initialization: {e}"
        )


# --- Scheduled Job Functions ---
# The job now needs to know *which* period's criteria to use.
# We can pass the period_details dict to the job.
def harmoniq_flow_job_wrapper(
    period_name_scheduled: str,
):  # Receives the name of the period it was scheduled for
    logger.info(
        f"Scheduler: Triggered Harmoniq Flow update job for scheduled period '{period_name_scheduled}'."
    )

    current_active_period_details = get_active_period_details()

    if not current_active_period_details:
        logger.error(
            f"Scheduler: Could not determine active period details for job '{period_name_scheduled}'. Skipping."
        )
        return

    logger.info(
        f"Scheduler: Running Harmoniq Flow for current active period '{current_active_period_details['name']}' (triggered by schedule for '{period_name_scheduled}')."
    )

    if plex_client_global and valid_music_libraries_global:
        try:
            # Pass the fully processed current_active_period_details, which includes 'hours_set'
            run_harmoniq_flow_update(
                plex_client_global,
                valid_music_libraries_global,
                target_library_global,
                current_active_period_details,
            )
        except Exception as e:
            logger.exception(
                f"Scheduler: Error during harmoniq_flow_job for period '{current_active_period_details['name']}' execution."
            )
    else:
        logger.warning(
            f"Scheduler: Skipping Harmoniq Flow job for period '{current_active_period_details['name']}' due to missing Plex client or libraries."
        )
    logger.info(
        f"Scheduler: Harmoniq Flow update job for period '{current_active_period_details['name']}' finished."
    )


def library_grower_job_wrapper():
    """Wrapper function for the Library Grower scheduled job."""
    logger.info("Scheduler: Triggered Library Grower discovery cycle job.")

    if not config.ENABLE_LIBRARY_GROWER:
        logger.info("Scheduler: Library Grower is disabled, skipping job.")
        return

    if not discovery_engine_global:
        logger.error("Scheduler: Discovery engine not initialized, skipping job.")
        return

    try:
        import asyncio

        asyncio.run(discovery_engine_global.run_discovery_cycle())
        logger.info(
            "Scheduler: Library Grower discovery cycle job completed successfully."
        )
    except Exception as e:
        logger.exception(
            f"Scheduler: Error during Library Grower discovery job execution: {e}"
        )


if __name__ == "__main__":
    logger.info("🎵 Harmoniq Multi-Job Scheduler starting...")
    logger.info(
        "🌐 Web UI will be available at http://localhost:7845 (if web server is running)"
    )

    from .stats_tracker import get_stats_tracker

    stats_tracker = get_stats_tracker()
    stats_tracker.record_system_start()

    initialize_global_clients_and_libs()

    # --- Schedule Harmoniq Flow Updates based on SCHEDULED_PERIODS ---
    if config.ENABLE_TIME_PLAYLIST and config.SCHEDULED_PERIODS:
        logger.info(
            f"Found {len(config.SCHEDULED_PERIODS)} periods to schedule for Harmoniq Flow."
        )
        for (
            period_config_detail
        ) in (
            config.SCHEDULED_PERIODS
        ):  # This dict from config only has name, start_hour, criteria
            start_hour_str = f"{period_config_detail['start_hour']:02d}:00"
            period_name_for_schedule = period_config_detail["name"]
            logger.info(
                f"Scheduling Harmoniq Flow update for period '{period_name_for_schedule}' at {start_hour_str} ({config.TIMEZONE})."
            )
            # Pass only the name of the period this schedule is FOR.
            # The job itself will determine the *currently* active period when it runs.
            schedule.every().day.at(start_hour_str, config.TIMEZONE).do(
                harmoniq_flow_job_wrapper,
                period_name_scheduled=period_name_for_schedule,
            )
    elif config.ENABLE_TIME_PLAYLIST:
        logger.warning(
            "Harmoniq Flow is enabled, but no periods were parsed from TIME_PERIOD_SCHEDULE. Flow updates will not be scheduled."
        )
    else:
        logger.info("Harmoniq Flow playlist updates are disabled.")

    # --- Schedule Library Grower Updates ---
    if config.ENABLE_LIBRARY_GROWER:
        interval_hours = config.LIBRARY_GROWER_RUN_INTERVAL_HOURS
        logger.info(f"Scheduling Library Grower to run every {interval_hours} hours.")
        schedule.every(interval_hours).hours.do(library_grower_job_wrapper)
    else:
        logger.info("Library Grower is disabled.")

    # --- Initial Run of Jobs ---
    logger.info("Performing initial run of jobs at startup...")
    if config.ENABLE_TIME_PLAYLIST:
        logger.info("Initial run: Harmoniq Flow update (for current period)...")
        initial_active_period = get_active_period_details()  # Get full details
        if initial_active_period:
            # Call the wrapper, which will then call run_harmoniq_flow_update with these full details
            harmoniq_flow_job_wrapper(
                initial_active_period["name"]
            )  # Pass the name, wrapper will call get_active_period_details
        else:
            logger.warning(
                "Initial run: No active period found for Harmoniq Flow, skipping."
            )
    if config.ENABLE_LIBRARY_GROWER:
        logger.info("Initial run: Library Grower cycle...")
        library_grower_job_wrapper()
    logger.info("Initial job runs complete. Waiting for scheduled runs...")

    while not shutdown_event_triggered:
        n = schedule.idle_seconds()
        if n is None:
            logger.info("No jobs scheduled. Scheduler idling...")
            time.sleep(60)  # Sleep longer if no jobs
            if (
                not schedule.jobs and not shutdown_event_triggered
            ):  # Double check after sleep
                logger.warning("No jobs remain scheduled. Exiting scheduler.")
                break
        elif n > 0:
            time.sleep(min(n, 1.0))
        if shutdown_event_triggered:
            break
        schedule.run_pending()
    logger.info("🛑 Harmoniq Scheduler has been shut down.")
