# Harmoniq

<!-- Add badges here (Build Status, License, Docker Hub pulls, etc.) -->
<!-- [![Build Status](...)](...) -->
<!-- [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) -->

Automated playlist generator for Plex (and eventually Jellyfin) using data from Last.fm and your Plex library's sonic analysis features. Harmoniq runs as a background service, keeping your self-hosted music library fresh with dynamic and smart playlists.

## The Problem

Do you love your self-hosted music setup with Plex or Jellyfin but miss the automatically curated playlists like "Discover Weekly," "Daily Mix," or "Top Charts" from streaming services? Manually creating playlists based on recommendations, charts, or your current mood can be tedious.

## The Solution

**Harmoniq** is a continuously running background service that connects to Last.fm and your Plex Media Server. It automatically generates and updates playlists in Plex based on various configurable criteria, bringing the convenience and dynamism of streaming service playlists to your own library.

**(Note on ListenBrainz:** Initial attempts to integrate ListenBrainz recommendations and playlists were unsuccessful due to unavailable or non-functional public API endpoints. Support may be revisited if the ListenBrainz API situation changes.)

## Core Features

*   **Continuous Operation & Scheduling:** Runs as a persistent background service, automatically updating playlists at a user-defined interval.
*   **Time-Based "Daily Flow" Playlist:**
    *   Generates a dynamic playlist that changes its content based on the time of day.
    *   Uses configurable time windows (e.g., "Morning Chill," "Afternoon Energy").
    *   Selects tracks from your Plex library based on **Moods** and **Genres/Styles** (requires Plex Sonic Analysis to be enabled and completed).
    *   Refines track selection by minimum star rating (includes unrated), recency (excluding recently played), and skip count.
*   **Last.fm Integration (Optional):**
    *   Creates playlists based on global chart data (Top Tracks).
    *   Creates *derived* recommendation playlists via similar artists logic (User Top Artists -> Similar Artists -> Top Tracks).
*   **(Planned) Advanced Sonic Similarity Playlists:** Future enhancements to create playlists with tracks that flow sonically.
*   **(Planned) Custom Logic Integration:** Hooks for incorporating your own playlist generation scripts.
*   **Plex Support:** Directly interacts with your Plex Media Server library (supports multiple music libraries).
*   **(Planned) Jellyfin Support:** Future goal to support Jellyfin servers.
*   **Dockerized:** Easy deployment as a containerized background service.
*   **Configurable:** Fine-tune behavior using environment variables (API keys, playlist names, sizes, schedules, features, refinement thresholds).
*   **Missing Track Logging:** Reports source tracks (from Last.fm) that weren't found in your library.

## Prerequisites

*   **Docker:** Docker and Docker Compose installed on your system.
*   **Plex Media Server:** A running instance accessible via network from the Docker container.
    *   **Sonic Analysis:** For the "Daily Flow" playlist to function effectively with Moods/Styles, ensure you have enabled and completed "Analyze audio features for Sonic Adventure" in your Plex music library settings.
*   **Plex Token:** Your [Plex Authentication Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
*   **Last.fm Account & API Key (Optional but Recommended for some features):**
    *   Required for global charts (`ENABLE_LASTFM_CHARTS=true`) or derived recommendations (`ENABLE_LASTFM_RECS=true`).
    *   API Key (Get one [here](https://www.last.fm/api/account/create))
    *   Your Last.fm Username

## Installation & Setup (Docker Compose Recommended)

1.  Create a `docker-compose.yml` file:

    ```yaml
    version: '3.7'

    services:
      harmoniq:
        # Replace 'your_username/harmoniq:latest' with the final image name/source 
        # if building locally or pulling from a registry.
        # If building from local source, ensure 'build' context is correct.
        image: harmoniq:latest # Example if you've built and tagged it
        # build:
        #   context: ./src  # Path to directory containing your Dockerfile
        #   dockerfile: Dockerfile
        container_name: harmoniq
        restart: unless-stopped # Keeps the service running
        env_file:
          - .env # Load environment variables from .env file
        # environment: # Optionally override or add variables here
        #   - LOG_LEVEL=DEBUG 
        # volumes: # Optional: if you need persistent logs outside the container
        #   - ./logs:/app/logs 
    ```

2.  Create a `.env` file in the same directory as `docker-compose.yml` (copy from `.env.example` provided in the repository and fill in your values):

    ```dotenv
    # .env - Harmoniq Configuration (Review .env.example for all options)

    PLEX_URL=http://YOUR_PLEX_IP:32400
    PLEX_TOKEN=YOUR_PLEX_TOKEN
    PLEX_MUSIC_LIBRARY_NAMES=Music # Comma-separated list

    RUN_INTERVAL_MINUTES=1440 # How often to update playlists (e.g., 1440 for daily)
    TIMEZONE=UTC              # e.g., America/New_York, Europe/London

    LASTFM_API_KEY=YOUR_LASTFM_API_KEY # Required if Last.fm features are enabled
    LASTFM_USER=YOUR_LASTFM_USERNAME   # Required if Last.fm features are enabled

    ENABLE_TIME_PLAYLIST=true
    ENABLE_LASTFM_RECS=true
    ENABLE_LASTFM_CHARTS=true
    
    # Playlist Names & Sizes (see .env.example for more)
    PLAYLIST_NAME_TIME=Daily Flow
    PLAYLIST_SIZE_TIME=40
    # Time Playlist Refinements
    TIME_PLAYLIST_MIN_RATING=3 # 0-5 stars, 0=disable, unrated tracks included if >0
    TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS=30 # 0=disable
    TIME_PLAYLIST_MAX_SKIP_COUNT=5       # High value like 999 to disable

    LOG_LEVEL=INFO 
    # TIME_WINDOWS="00:00-09:00:moods=Chill;09:00-17:00:moods=Energetic;17:00-00:00:moods=Atmospheric" 
    # (See .env.example for full TIME_WINDOWS format)
    ```

3.  **(Build Image Locally - if needed, and `build:` context is in docker-compose.yml):**
    ```bash
    docker-compose build harmoniq 
    ```
    (Or let `up --build` handle it the first time if you don't specify `image:`).

4.  **Run the container:**
    ```bash
    # Start in detached mode
    docker-compose up -d

    # To view logs:
    docker-compose logs -f harmoniq

    # To stop:
    docker-compose stop harmoniq

    # To stop and remove:
    docker-compose down
    ```

## Configuration

Harmoniq is configured entirely through **environment variables**, preferably set in the `.env` file used by `docker-compose.yml`. Refer to the `.env.example` file in the repository for a comprehensive list of all available options and their descriptions.

**Key Variable Groups:**

*   **Plex Connection:** `PLEX_URL`, `PLEX_TOKEN`, `PLEX_MUSIC_LIBRARY_NAMES`.
*   **Scheduler:** `RUN_INTERVAL_MINUTES`, `TIMEZONE`.
*   **Last.fm Connection:** `LASTFM_API_KEY`, `LASTFM_USER`.
*   **Feature Flags:** `ENABLE_TIME_PLAYLIST`, `ENABLE_LASTFM_RECS`, `ENABLE_LASTFM_CHARTS`.
*   **Playlist Naming & Sizing:** `PLAYLIST_NAME_*`, `PLAYLIST_SIZE_*`.
*   **Time Playlist Specifics:** `TIME_WINDOWS`, `TIME_PLAYLIST_MIN_RATING`, `TIME_PLAYLIST_EXCLUDE_PLAYED_DAYS`, `TIME_PLAYLIST_MAX_SKIP_COUNT`.
*   **Logging:** `LOG_LEVEL`.

**Security Note:** Treat your `PLEX_TOKEN` and `LASTFM_API_KEY` as sensitive secrets. Use the `.env` file or secure environment variable management; do not commit them directly into version control.

## Usage

Once configured and started via `docker-compose up -d`, Harmoniq runs as a persistent background service.
1.  On startup, it will perform an initial run of all enabled playlist generation tasks.
2.  Subsequently, it will trigger these tasks again every `RUN_INTERVAL_MINUTES`.

Look for the generated playlists (e.g., "Daily Flow", "Last.fm Discovery") in your Plex client apps. The logs will indicate when updates occur and if any issues are encountered.

## Roadmap

See the [Roadmap.md](Roadmap.md) file for planned features, improvements, and development phases. Current priorities include refining existing features, improving error handling, and exploring advanced sonic similarity integration.

## Contributing

Contributions are welcome! Whether it's bug reports, feature suggestions, or code contributions:

1.  Please check for existing issues before opening a new one.
2.  Feel free to open an issue to discuss proposed changes.
3.  Submit pull requests against the `main` (or `develop`) branch.

## License

This project is licensed under the [**CHOOSE A LICENSE - e.g., MIT License**]. See the [LICENSE](LICENSE) file for details.
*(Remember to add a LICENSE file, e.g., MIT)*

## Acknowledgements

*   Built with Python.
*   Key libraries: [python-plexapi](https://github.com/pkkid/python-plexapi), [Requests](https://requests.readthedocs.io/en/latest/), [schedule](https://schedule.readthedocs.io/en/stable/), [pytz](https://pythonhosted.org/pytz/).
*   Thanks to Last.fm for their public API and Plex for the rich metadata accessible via Sonic Analysis.