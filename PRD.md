# PRD: Harmoniq

**Version:** 1.1

## 1. Introduction & Purpose

This document outlines the requirements for the "Harmoniq", a standalone, containerized application. The primary purpose of Harmoniq is to automatically create and update dynamic playlists within a user's Plex Media Server, mimicking popular features found in commercial streaming services (e.g., Discovery Mix, Top Charts, time-based flows). It leverages data from external services like Last.fm and ListenBrainz, combined with the user's existing Plex library content, and runs as a persistent background service.

## 2. Goals

*   **Automate Playlist Creation:** Eliminate the manual effort of creating discovery and topical playlists in Plex.
*   **Enhance Music Discovery:** Provide users with relevant music recommendations based on their listening habits (via Last.fm/ListenBrainz) and popular trends, sourced from within their own library.
*   **Mimic Streaming Service Experience:** Replicate the convenience of auto-updating playlists like "My Mix," "Discovery Weekly," "Top Charts," and introduce a time-sensitive dynamic "Flow" playlist.
*   **Continuous Operation:** Run as a persistent service that automatically updates playlists on a defined schedule.
*   **Easy Deployment:** Provide a containerized solution (Docker) for simple setup and management.
*   **Configurability:** Allow users to easily configure connections, playlist types, scheduling, and behavior via environment variables.
*   **Transparency:** Log actions clearly and identify tracks that were recommended but not found in the user's library (useful for manual acquisition or potential Lidarr integration).

## 3. User Stories

*   As a Plex user, I want to configure Harmoniq with my Plex server details and API keys for Last.fm/ListenBrainz so that it can access my library and fetch recommendations.
*   As a Plex user, I want Harmoniq to automatically create/update a playlist named "Discovery Mix" based on my Last.fm recommendations, containing tracks that exist in my Plex library.
*   As a Plex user, I want Harmoniq to automatically create/update a playlist named "Global Top Tracks" based on Last.fm's chart data, containing tracks that exist in my Plex library.
*   As a Plex user, I want to configure which types of playlists Harmoniq should manage (e.g., enable Discovery, disable Charts).
*   As a Plex user, I want Harmoniq to run continuously in its Docker container, automatically refreshing playlists every X hours/minutes based on my configuration.
*   As a Plex user, I want to configure the time interval at which Harmoniq checks and updates playlists.
*   As a Plex user, I want Harmoniq to manage a special playlist (e.g., "Daily Flow") whose content changes based on the time of day (e.g., calmer music in the morning, more energetic in the afternoon).
*   As a Plex user, I want to configure the time windows (e.g., 6 AM - 11 AM, 11 AM - 5 PM) for the "Daily Flow" playlist.
*   As a Plex user, I want to define criteria (e.g., specific genres, Last.fm tags) for the music suitable for each time window in the "Daily Flow" playlist.
*   As a Plex user, I want Harmoniq to log which recommended tracks could *not* be found in my Plex library, so I know what I might be missing.
*   As a Plex user, I want to deploy Harmoniq easily using Docker.
*   (Future) As a Plex user, I want to integrate my custom "Forgotten Gems" playlist logic into Harmoniq.
*   (Future) As a Plex user, I want Harmoniq to fetch recommendations from ListenBrainz as an alternative or supplement to Last.fm.

## 4. Functional Requirements

*   **FR1: Configuration:**
    *   The application MUST allow configuration via environment variables (Docker standard).
    *   Required configurations: `PLEX_URL`, `PLEX_TOKEN`, `PLEX_MUSIC_LIBRARY_NAME(S)`.
    *   Optional configurations: `LASTFM_API_KEY`, `LASTFM_USER`, `LISTENBRAINZ_USER_TOKEN`.
    *   Configuration MUST allow enabling/disabling specific playlist generator types (e.g., `ENABLE_LASTFM_RECS=true`, `ENABLE_LASTFM_CHARTS=false`, `ENABLE_TIME_PLAYLIST=true`, `ENABLE_LISTENBRAINZ_RECS=false`).
    *   Configuration MUST allow specifying the names for the generated Plex playlists (e.g., `PLAYLIST_NAME_LASTFM_RECS="Last.fm Discovery"`, `PLAYLIST_NAME_TIME="Daily Flow"`).
    *   Configuration MUST allow setting the approximate number of tracks to target for each playlist type (e.g., `PLAYLIST_SIZE_RECS=30`, `PLAYLIST_SIZE_CHARTS=50`).
    *   Configuration MUST include `RUN_INTERVAL_MINUTES` (e.g., `1440` for daily, `60` for hourly) defining the frequency of playlist updates.
    *   Configuration MUST include `TIMEZONE` (e.g., `America/New_York`, `UTC`) to correctly interpret time for scheduled tasks and time-based playlists. Defaults to UTC if not set.
    *   Configuration MUST allow defining time windows and associated criteria for the time-based playlist. The exact format needs design, but conceptually: `TIME_WINDOWS="00:00-06:00:genres=Ambient,Sleep;06:00-11:00:genres=Chillout,Acoustic;11:00-17:00:tags=upbeat,rock;17:00-24:00:genres=Jazz,Classical"`.

*   **FR2: Data Fetching:**
    *   The application MUST be able to fetch user track recommendations from Last.fm (`user.getrecommendedtracks`).
    *   The application MUST be able to fetch global top tracks from Last.fm (`chart.gettoptracks`).
    *   (Future) The application SHOULD be able to fetch user track recommendations from ListenBrainz API.
    *   (Future) The application MAY need to fetch track tags/genres from Last.fm/MusicBrainz if Plex metadata is insufficient for `FR4`'s time-based playlist criteria.
    *   Fetching modules MUST handle API errors gracefully (e.g., network issues, invalid keys, rate limiting) and log them without crashing the service.

*   **FR3: Plex Interaction:**
    *   The application MUST connect to the specified Plex Media Server using the provided `PLEX_URL` and `PLEX_TOKEN`.
    *   The application MUST locate the specified Plex Music Library section(s) by name (`PLEX_MUSIC_LIBRARY_NAMES`).
    *   The application MUST search for tracks within the Plex library based on Artist and Title information obtained from external services.
    *   The application MUST be able to search/filter tracks in the Plex library based on metadata like `Genre` (primary) or potentially `Mood`/`Style` tags for the time-based playlist.
    *   The application MUST handle cases where a recommended track is not found in the Plex library (log it).
    *   The application MUST be able to create a new playlist in Plex if it doesn't exist.
    *   The application MUST be able to clear existing items from a target playlist before adding new ones (default behavior). Optional append/replace behavior could be a future enhancement.
    *   The application MUST add the found Plex track objects to the target playlist.
    *   The application SHOULD update the playlist summary/description (e.g., "Updated by Harmoniq on YYYY-MM-DD HH:MM").
    *   Plex interaction MUST handle errors gracefully (e.g., connection failed, library not found, permission issues) and log them without crashing the service.

*   **FR4: Playlist Generation Logic:**
    *   The application logic MUST process fetched recommendations/charts for each *enabled* playlist type.
    *   For each enabled playlist type, it MUST attempt to find matching tracks in Plex, respecting the configured `PLAYLIST_SIZE_*`.
    *   It MUST compile a list of found Plex track objects.
    *   It MUST use the Plex Interaction module (FR3) to update or create the corresponding playlist.
    *   The application MUST include specific logic for the time-based dynamic playlist (if `ENABLE_TIME_PLAYLIST=true`):
        *   Determine the current time based on the configured `TIMEZONE`.
        *   Identify the active time window based on `TIME_WINDOWS` configuration.
        *   Retrieve the criteria (genres, tags, etc.) for the active window.
        *   Select tracks from the Plex library matching these criteria (selection strategy: initially random sample, potentially refine later).
        *   Update the single designated time-based playlist (`PLAYLIST_NAME_TIME`) with these tracks, respecting `PLAYLIST_SIZE_TIME`.

*   **FR5: Scheduling & Execution:**
    *   The application MUST run as a persistent process within the container.
    *   It MUST use an internal scheduling mechanism (e.g., Python's `schedule` library or `APScheduler`) to trigger playlist update tasks based on the `RUN_INTERVAL_MINUTES` configuration.
    *   The scheduler MUST run the update logic for *all* enabled playlist types sequentially during each interval tick.
    *   The scheduler SHOULD prevent concurrent runs of the *entire* update cycle if the previous cycle hasn't finished (e.g., using a simple lock or checking scheduler job status).
    *   The main process MUST handle termination signals (e.g., SIGTERM from `docker stop`) gracefully to allow clean shutdown of the scheduler and current tasks if possible.

*   **FR6: Logging:**
    *   The application MUST log its startup, configuration loading (masking sensitive keys), scheduler activity, and actions taken (e.g., "INFO: Starting playlist update cycle.", "INFO: Fetching Last.fm Recs...", "INFO: Updating playlist 'Discovery Mix' with 25 tracks.").
    *   It MUST log the number of recommendations fetched and the number of tracks successfully matched and added to Plex for each playlist.
    *   It MUST clearly log tracks that were recommended but could not be found in the Plex library (e.g., "WARNING: Track not found in Plex: [Artist Name] - [Track Title]"). This could optionally be directed to a separate log file or structured output later.
    *   It MUST log any significant errors encountered during API calls, Plex interactions, or scheduling (e.g., "ERROR: Failed to connect to Plex: [details]", "ERROR: Last.fm API error: [details]").
    *   Logging MUST be directed to standard output (stdout) / standard error (stderr) for Docker compatibility. Log levels (DEBUG, INFO, WARNING, ERROR) should be used appropriately.

*   **FR7: Dockerization:**
    *   A `Dockerfile` MUST be provided to build the application image.
    *   The image SHOULD be based on a standard Python base image (e.g., `python:3.10-slim`).
    *   All dependencies MUST be managed via `requirements.txt`.
    *   The `Dockerfile` `CMD` or `ENTRYPOINT` MUST start the long-running scheduler process.

## 5. Non-Functional Requirements

*   **NFR1: Reliability:** The application must run stably as a long-running service. Robust error handling within the main loop and scheduled tasks is essential to prevent crashes from single playlist failures or API issues.
*   **NFR2: Maintainability:** Code should be modular (e.g., separate modules/functions for config, data sources, plex api, playlist logic, scheduler) and include comments for complex parts.
*   **NFR3: Performance:** Be mindful of external API rate limits; implement delays if necessary. Plex searches should be reasonably efficient. Avoid resource leaks (memory, connections) in the long-running process.
*   **NFR4: Security:** API keys and tokens MUST be handled securely via environment variables and MUST NOT be logged directly.

## 6. Out of Scope (for V1.1 Release)

*   Direct integration with Lidarr/Radarr/Sonarr (logging missing tracks provides the hook for external scripts).
*   Web UI for configuration or monitoring.
*   Advanced track matching heuristics (e.g., fuzzy matching, duration matching, MusicBrainz ID matching).
*   Support for video libraries or photo libraries in Plex.
*   Real-time playlist updates triggered by external events.
*   User authentication layer within the tool itself (relies on Plex token security).
*   Complex audio analysis (tempo, mood detection) for time-based playlists (rely on existing metadata/tags first).
*   Highly granular time windows (e.g., updates every 5 minutes) might be inefficient initially.
*   Alternative playlist update modes (append, rotate) - default is clear and replace.