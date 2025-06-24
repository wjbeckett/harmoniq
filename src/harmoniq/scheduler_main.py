# src/harmoniq/scheduler_main.py
import schedule
import time
import signal
import logging

from .main import run_harmoniq_flow_update, run_external_services_update, get_active_period_details
from .plex_client import PlexClient
from .lastfm_client import LastfmClient
from . import config
from .log_config import logger

shutdown_event_triggered = False
def handle_shutdown_signal(signum, frame):
    global shutdown_event_triggered
    if not shutdown_event_triggered:
        logger.info(f"Shutdown signal ({signal.Signals(signum).name}) received. Finishing current jobs and shutting down...")
        shutdown_event_triggered = True
        schedule.clear() 
    else: logger.info("Multiple shutdown signals received.")

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

plex_client_global = None
lastfm_client_global = None
valid_music_libraries_global = []
target_library_global = None

def initialize_global_clients_and_libs():
    global plex_client_global, lastfm_client_global, valid_music_libraries_global, target_library_global
    logger.info("Scheduler: Initializing global Plex and Last.fm clients...")
    valid_music_libraries_global = [] # Reset for re-initialization if ever called again
    try:
        plex_client_global = PlexClient()
        if config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS:
            if config.LASTFM_API_KEY and config.LASTFM_USER:
                lastfm_client_global = LastfmClient()
            else: logger.warning("Scheduler: Last.fm client not initialized (API Key/User missing).")
        
        if plex_client_global:
            for name in config.PLEX_MUSIC_LIBRARY_NAMES:
                lib = plex_client_global.get_music_library(name)
                if lib: valid_music_libraries_global.append(lib)
            if valid_music_libraries_global:
                target_library_global = valid_music_libraries_global[0]
                logger.info(f"Scheduler: Accessed {len(valid_music_libraries_global)} Plex libraries. Target: '{target_library_global.title}'.")
            else: logger.error("Scheduler: Could not access any valid Plex music libraries.")
        else: logger.error("Scheduler: Plex client failed to initialize.")
    except Exception as e: logger.exception(f"Scheduler: Critical error during global client initialization: {e}")

# --- Scheduled Job Functions ---
# The job now needs to know *which* period's criteria to use.
# We can pass the period_details dict to the job.
def harmoniq_flow_job_wrapper(period_name_scheduled: str): # Receives the name of the period it was scheduled for
    logger.info(f"Scheduler: Triggered Harmoniq Flow update job for scheduled period '{period_name_scheduled}'.")
    
    current_active_period_details = get_active_period_details()

    if not current_active_period_details:
        logger.error(f"Scheduler: Could not determine active period details for job '{period_name_scheduled}'. Skipping.")
        return

    logger.info(f"Scheduler: Running Harmoniq Flow for current active period '{current_active_period_details['name']}' (triggered by schedule for '{period_name_scheduled}').")

    if plex_client_global and valid_music_libraries_global:
        try:
            # Pass the fully processed current_active_period_details, which includes 'hours_set'
            run_harmoniq_flow_update(plex_client_global, valid_music_libraries_global, target_library_global, current_active_period_details)
        except Exception as e:
            logger.exception(f"Scheduler: Error during harmoniq_flow_job for period '{current_active_period_details['name']}' execution.")
    else:
        logger.warning(f"Scheduler: Skipping Harmoniq Flow job for period '{current_active_period_details['name']}' due to missing Plex client or libraries.")
    logger.info(f"Scheduler: Harmoniq Flow update job for period '{current_active_period_details['name']}' finished.")

def external_services_job():
    # (This job remains the same)
    logger.info("Scheduler: Triggered External Services update job.")
    if plex_client_global and valid_music_libraries_global:
        try:
            run_external_services_update(plex_client_global, lastfm_client_global, valid_music_libraries_global, target_library_global)
        except Exception as e: logger.exception("Scheduler: Error during external_services_job execution.")
    else: logger.warning("Scheduler: Skipping External Services job due to missing Plex client or libraries.")
    logger.info("Scheduler: External Services update job finished.")

if __name__ == "__main__":
    logger.info("Harmoniq Multi-Job Scheduler starting...")
    initialize_global_clients_and_libs()

    # --- Schedule Harmoniq Flow Updates based on SCHEDULED_PERIODS ---
    if config.ENABLE_TIME_PLAYLIST and config.SCHEDULED_PERIODS:
        logger.info(f"Found {len(config.SCHEDULED_PERIODS)} periods to schedule for Harmoniq Flow.")
        for period_config_detail in config.SCHEDULED_PERIODS: # This dict from config only has name, start_hour, criteria
            start_hour_str = f"{period_config_detail['start_hour']:02d}:00"
            period_name_for_schedule = period_config_detail['name']
            logger.info(f"Scheduling Harmoniq Flow update for period '{period_name_for_schedule}' at {start_hour_str} ({config.TIMEZONE}).")
            # Pass only the name of the period this schedule is FOR.
            # The job itself will determine the *currently* active period when it runs.
            schedule.every().day.at(start_hour_str, config.TIMEZONE).do(harmoniq_flow_job_wrapper, period_name_scheduled=period_name_for_schedule)
    elif config.ENABLE_TIME_PLAYLIST:
        logger.warning("Harmoniq Flow is enabled, but no periods were parsed from TIME_PERIOD_SCHEDULE. Flow updates will not be scheduled.")
    else:
        logger.info("Harmoniq Flow playlist updates are disabled.")

    # --- Schedule External Services (Last.fm) Update ---
    # (This scheduling logic remains the same)
    if (config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS) and config.RUN_INTERVAL_MINUTES > 0:
        logger.info(f"Scheduling External Services (Last.fm) to run every {config.RUN_INTERVAL_MINUTES} minutes.")
        schedule.every(config.RUN_INTERVAL_MINUTES).minutes.do(external_services_job)
    elif (config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS) and config.RUN_INTERVAL_MINUTES <= 0 :
        logger.info("External Services (Last.fm) RUN_INTERVAL_MINUTES <= 0. Will only run once if enabled (during initial run).")
    else: logger.info("Last.fm features disabled, not scheduling external services job.")

    # --- Initial Run of Jobs ---
    logger.info("Performing initial run of jobs at startup...")
    if config.ENABLE_TIME_PLAYLIST:
        logger.info("Initial run: Harmoniq Flow update (for current period)...")
        initial_active_period = get_active_period_details() # Get full details
        if initial_active_period:
            # Call the wrapper, which will then call run_harmoniq_flow_update with these full details
            harmoniq_flow_job_wrapper(initial_active_period['name']) # Pass the name, wrapper will call get_active_period_details
        else:
            logger.warning("Initial run: No active period found for Harmoniq Flow, skipping.")
            
    if config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS:
        logger.info("Initial run: External Services (Last.fm) update...")
        external_services_job()
    logger.info("Initial job runs complete. Waiting for scheduled runs...")

    # --- Main Scheduler Loop (remains the same) ---
    while not shutdown_event_triggered:
        n = schedule.idle_seconds()
        if n is None: 
            logger.info("No jobs scheduled. Scheduler idling...")
            time.sleep(60) # Sleep longer if no jobs
            if not schedule.jobs and not shutdown_event_triggered : # Double check after sleep
                 logger.warning("No jobs remain scheduled. Exiting scheduler.")
                 break
        elif n > 0:
            time.sleep(min(n, 1.0))
        if shutdown_event_triggered: break
        schedule.run_pending()
    logger.info("Harmoniq Scheduler has been shut down.")