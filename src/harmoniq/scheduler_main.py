# src/harmoniq/scheduler_main.py
import schedule
import time
import signal
import logging

# Import the main update function and config (which loads env vars)
from .main import run_playlist_update_cycle
from . import config # This ensures config is loaded, including log_config
from .log_config import logger # Use the globally configured logger

# --- Graceful Shutdown Handling ---
shutdown_event_triggered = False

def handle_shutdown_signal(signum, frame):
    global shutdown_event_triggered
    if not shutdown_event_triggered:
        logger.info(f"Shutdown signal ({signal.Signals(signum).name}) received. Shutting down gracefully...")
        shutdown_event_triggered = True
        # Note: schedule library doesn't have a direct 'stop all jobs and exit'
        # The main loop will exit on the next check of shutdown_event_triggered
    else:
        logger.info("Multiple shutdown signals received. Forcing exit if necessary.")

# Register signal handlers
signal.signal(signal.SIGINT, handle_shutdown_signal)  # Handle Ctrl+C
signal.signal(signal.SIGTERM, handle_shutdown_signal) # Handle `docker stop`

def job():
    """Wrapper for the scheduled job."""
    logger.info("Scheduler triggered: Starting playlist update cycle.")
    try:
        run_playlist_update_cycle()
    except Exception as e:
        logger.exception(f"An unexpected error occurred within the scheduled job: {e}")
    logger.info("Scheduled job: Playlist update cycle finished.")

if __name__ == "__main__":
    logger.info(f"Harmoniq Scheduler starting. Update interval: {config.RUN_INTERVAL_MINUTES} minutes.")
    
    if config.RUN_INTERVAL_MINUTES <= 0:
        logger.warning("RUN_INTERVAL_MINUTES is not positive. Scheduler will run the job once and exit.")
        job()
        logger.info("Harmoniq Scheduler finished (single run due to interval <= 0).")
    else:
        # Schedule the job
        schedule.every(config.RUN_INTERVAL_MINUTES).minutes.do(job)
        logger.info(f"Job scheduled to run every {config.RUN_INTERVAL_MINUTES} minutes. First run will be at the next interval.")
        
        # Run the job once immediately at startup (optional, but good for quick feedback)
        logger.info("Running job once immediately at startup...")
        job()
        logger.info("Initial startup job finished. Waiting for next scheduled run...")

        while not shutdown_event_triggered:
            # Run any pending scheduled tasks
            # schedule.run_pending() will execute job() if it's time
            schedule.run_pending()
            
            # Sleep for a short interval to avoid busy-waiting
            # Check for shutdown more frequently than the main job interval
            # How long to sleep? If interval is very short, make this shorter.
            # If interval is long, this can be longer but check shutdown_event_triggered.
            # Let's check every second.
            for _ in range(min(60, config.RUN_INTERVAL_MINUTES * 60 // 2 if config.RUN_INTERVAL_MINUTES > 0 else 60)): # Sleep for up to 1 min, or half the interval
                if shutdown_event_triggered:
                    break
                time.sleep(1)
            if shutdown_event_triggered:
                 break
        
        logger.info("Harmoniq Scheduler has been shut down.")