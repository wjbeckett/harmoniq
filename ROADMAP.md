# Roadmap: Harmoniq

This roadmap outlines the planned development phases for the Harmoniq.

## Phase 1: MVP - Core Last.fm Recs & Single Run

*   **Target Timeframe:** ~1 week
*   **Features:**
    *   Basic Python project structure (`src/`, `tests/`, etc.).
    *   Configuration loading via environment variables (`PLEX_URL`, `PLEX_TOKEN`, `PLEX_MUSIC_LIBRARY_NAME`, `LASTFM_API_KEY`, `LASTFM_USER`, `PLAYLIST_NAME_LASTFM_RECS`, `PLAYLIST_SIZE_RECS`).
    *   Implement `fetch_lastfm_recommendations` function using `requests`.
    *   Implement core Plex connection logic using `python-plexapi`.
    *   Implement `find_plex_track` function (basic Artist/Title matching).
    *   Implement `update_plex_playlist` function (create if not exists, clear & add items).
    *   Basic logging to stdout (INFO level for major steps, WARNING for missing tracks, ERROR for failures).
    *   Initial `Dockerfile` for building the image.
    *   `requirements.txt` for managing dependencies (`requests`, `python-plexapi`).
    *   Entrypoint script (`main.py`) that performs the fetch -> match -> update sequence **once** for Last.fm recommendations and then exits.
*   **Goal:** Prove the core concept works end-to-end. A user can build and run the container, and it successfully creates or updates *one* specific playlist ("Last.fm Discovery") based on their Last.fm recommendations found in Plex, then the container stops.

## Phase 2: Internal Scheduling & Continuous Operation

*   **Target Timeframe:** ~1 week (after Phase 1 completion)
*   **Features:**
    *   Integrate a scheduling library (e.g., `schedule` or `APScheduler`).
    *   Add `RUN_INTERVAL_MINUTES` and `TIMEZONE` environment variable configurations.
    *   Refactor the core logic from Phase 1 into a function (e.g., `run_playlist_update_cycle`) that can be called by the scheduler.
    *   Implement the main persistent process loop (`while True: schedule.run_pending(); time.sleep(1)`).
    *   Implement graceful shutdown handling for SIGTERM signals (stop the scheduler, allow current job to finish if feasible).
    *   Update `Dockerfile` `CMD` to execute the persistent scheduler script.
    *   Implement robust error handling *within* the scheduled task function (`run_playlist_update_cycle`) using `try...except` blocks to catch API/Plex errors, log them, and allow the scheduler to continue running for the next interval.
    *   Add logging for scheduler startup and job execution triggers.
*   **Goal:** Transform the application into a continuously running service within the Docker container. The service periodically updates the *existing* Last.fm Discovery playlist based on the configured interval.

## Phase 3: Expanding Playlist Types (Last.fm Charts)

*   **Target Timeframe:** ~1 week (after Phase 2 completion)
*   **Features:**
    *   Implement `fetch_lastfm_charts` function (`chart.gettoptracks`).
    *   Modify the `run_playlist_update_cycle` function (or create helper functions) to handle multiple, distinct playlist generation tasks based on configuration.
    *   Add environment variables: `ENABLE_LASTFM_CHARTS`, `PLAYLIST_NAME_LASTFM_CHARTS`, `PLAYLIST_SIZE_CHARTS`.
    *   Update the main scheduled task to iterate through *enabled* playlist types and call the appropriate fetch/update logic for each.
    *   Enhance logging to clearly distinguish actions/results for different playlist types (e.g., "[LastfmRecs] Found 30 tracks", "[LastfmCharts] Updating playlist 'Global Top 50'...").
*   **Goal:** Support multiple, configurable playlist types (initially Last.fm Recs and Charts) updated automatically by the persistent scheduler.

## Phase 4: Time-Based Dynamic Playlist ("Daily Flow")

*   **Target Timeframe:** ~2-3 weeks (after Phase 3 completion)
*   **Features:**
    *   Design and implement the parsing logic for the `TIME_WINDOWS` environment variable string.
    *   Implement logic to determine the current time window based on the system time (adjusted for `TIMEZONE`).
    *   Implement Plex track searching/filtering based on `Genre` metadata (using `plexapi` search filters). Support for multiple genres per window.
    *   Develop the track selection strategy for the time window (e.g., find all matching tracks, then take a random sample up to `PLAYLIST_SIZE_TIME`).
    *   Integrate this logic as a new playlist type within the `run_playlist_update_cycle` function, controlled by `ENABLE_TIME_PLAYLIST`, `PLAYLIST_NAME_TIME`, `PLAYLIST_SIZE_TIME`.
    *   Ensure Plex genre searching is robust (handles case sensitivity, variations if possible).
    *   Add specific logging for the time-based playlist generation (e.g., "Active window: 06:00-11:00 (Criteria: genres=Chillout,Acoustic)", "Found 150 matching tracks, selecting 30 for 'Daily Flow'.").
*   **Goal:** Introduce the dynamic "Daily Flow" playlist feature, allowing users to have a single playlist that automatically updates its content based on the time of day and configured genre criteria.

## Phase 5: ListenBrainz & Custom Logic Integration (Potential Future)

*   **Target Timeframe:** ~2 weeks (after Phase 4 completion)
*   **Features:**
    *   Implement ListenBrainz recommendation fetching module (`fetch_listenbrainz_recommendations`) using their API.
    *   Add ListenBrainz configuration (`LISTENBRAINZ_USER_TOKEN`, `ENABLE_LISTENBRAINZ_RECS`, `PLAYLIST_NAME_LISTENBRAINZ_RECS`, `PLAYLIST_SIZE_LISTENBRAINZ_RECS`).
    *   Integrate ListenBrainz recommendations as another configurable playlist type in the scheduler.
    *   (Optional) Define an interface/method for users to plug in their own custom playlist logic (e.g., the "Forgotten Gems" script). This might involve mounting a custom script volume and calling it, or defining a specific function structure. Add associated enable flags (`ENABLE_CUSTOM_1`, `PLAYLIST_NAME_CUSTOM_1`, etc.).
    *   Potentially refine `find_plex_track` based on accumulated experience (e.g., handle common mismatches if identified).
*   **Goal:** Add ListenBrainz as an alternative/additional recommendation source and provide a basic mechanism for incorporating user-defined playlist logic.

## Phase 6: Polish, Optimization & Future Hooks (Ongoing / Post-Release)

*   **Target Timeframe:** Ongoing / Post-Phase 4/5
*   **Features:**
    *   Optimize Docker image size (e.g., multi-stage builds).
    *   Add a basic Docker health check endpoint/script.
    *   Refine logging: Consider structured logging (JSON), option for log levels via Env Var (`LOG_LEVEL=DEBUG`).
    *   Formalize the output of missing tracks (e.g., write to a persistent volume file `missing_tracks.log` or `missing_tracks.json`) to make Lidarr integration easier for external scripts.
    *   Investigate and potentially implement other useful playlist types (e.g., Last.fm `user.gettoptracks`, `user.gettopartists` -> other tracks by them).
    *   Code cleanup, add more comments, improve documentation (README.md with detailed setup and config).
    *   Add unit tests for core logic (config parsing, API parsing stubs, time window logic). Add basic integration tests (if feasible without a live Plex/API).
    *   Consider adding configuration for playlist update behavior (e.g., `PLAYLIST_UPDATE_MODE=replace` (default) vs `append`).
*   **Goal:** Improve stability, efficiency, usability, test coverage, documentation, and lay groundwork for potential future integrations and features.