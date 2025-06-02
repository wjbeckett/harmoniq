# Harmoniq

<!-- Badges: Build Status, License, Docker Hub/GHCR pulls -->
<!-- [![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/wjbeckett/harmoniq/main.yml?branch=main)](https://github.com/wjbeckett/harmoniq/actions) -->
<!-- [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) -->

Harmoniq is an automated playlist generator for your Plex Media Server, designed to bring the dynamic and personalized experience of streaming service playlists to your self-hosted music library. It leverages Plex's sonic analysis, your listening history, and (optionally) Last.fm data to create engaging, context-aware playlists that refresh automatically.

## Key Features

*   **"Harmoniq Flow" - Dynamic Time-Based Playlists:**
    *   Generates a central playlist (default name: "Harmoniq Flow") that adapts its vibe throughout the day.
    *   Uses **user-defined named periods** (e.g., "Morning Focus," "Evening Chill") with configurable start times.
    *   **Learned Vibe Augmentation:** Analyzes your listening history for each period and dynamically augments the target mood/style, making playlists more personalized over time.
    *   **Vibe & Familiar Anchors:** Selects "Vibe Anchors" (discovery tracks matching the period's augmented vibe) and "Familiar Anchors" (from your history, compatible with the vibe).
    *   **Sonic Adventure Bridging (Optional):** Utilizes Plex's `sonicAdventure` feature to create sonically flowing paths between anchor tracks.
    *   **Sonic Expansion (Optional):** Further expands the playlist with tracks sonically similar to selected seeds.
    *   **Refinement Filters:** Applies filters for minimum rating (includes unrated by default), recency (excludes recently played), and skip count.
    *   **Sonic Sort (Optional):** Can apply a greedy sonic sort for flow if `sonicAdventure` is not used or as a final polish.
*   **Last.fm Integration (Optional):**
    *   Creates "Last.fm Discovery" playlists based on derived recommendations (User Top Artists -> Similar Artists -> Top Tracks).
    *   Creates "Last.fm Global Charts" playlists.
*   **Continuous Operation & Scheduling:**
    *   Runs as a persistent background service.
    *   "Harmoniq Flow" updates at the start of each user-defined period.
    *   Last.fm playlists update based on a configurable interval.
*   **Plex Support:**
    *   Directly interacts with your Plex Media Server.
    *   Supports multiple Plex music libraries.
    *   Requires **Plex Sonic Analysis** to be enabled and completed for full "Harmoniq Flow" functionality (Moods, Styles, Sonic features).
*   **Configuration via YAML & Environment Variables:**
    *   Primary configuration via a `config.yaml` file for structured settings.
    *   Environment variables (and `.env` file) can be used for secrets and overrides.
*   **Dockerized:** Easy deployment using Docker and Docker Compose.
*   **Dynamic Playlist Covers (Optional):** Generates custom cover art for the "Harmoniq Flow" playlist based on the active period.
*   **(Planned) Missing Track Output, Other Playlist Types, Jellyfin Support.**

## Prerequisites

*   **Docker & Docker Compose.**
*   **Plex Media Server:**
    *   Network accessible.
    *   **Sonic Analysis enabled and run** on your music libraries for full "Harmoniq Flow" features.
*   **Plex Token:** [Find your token here](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
*   **(Optional) Last.fm Account & API Key:** If using Last.fm features.
    *   API Key: [Get one here](https://www.last.fm/api/account/create).
    *   Your Last.fm Username.

## Installation & Setup

1.  **Prepare Configuration:**
    *   Copy `config.yaml.example` from the repository to a directory on your host (e.g., `./harmoniq-config/config.yaml`).
    *   Edit your `config.yaml` to define your Plex server, music libraries, `TIME_PERIOD_SCHEDULE`, and other preferences. See `config.yaml.example` for all options and detailed comments.
    *   Copy `.env.example` to `.env` in your project root (or where `docker-compose.yml` will reside). Edit it to add your `PLEX_URL`, `PLEX_TOKEN`, and any Last.fm credentials.

2.  **Create `docker-compose.yml`:**

    ```yaml
    version: '3.7'

    services:
      harmoniq:
        # Option 1: Use a pre-built image (replace with actual image path if published)
        # image: your_dockerhub_username/harmoniq:latest
        # Option 2: Build from local source
        build:
          context: . # Or ./src if your Dockerfile is in a 'src' subdirectory
          dockerfile: Dockerfile # Assuming Dockerfile is in the context path
        container_name: harmoniq
        restart: unless-stopped
        env_file:
          - .env # For secrets and top-level overrides
        volumes:
          # Mount your local config directory to /app/config inside the container
          - ./harmoniq-config:/app/config:ro # Mount as read-only
          # Optional: Mount a directory for fonts if you want to use custom fonts for covers
          # - ./my_fonts:/app/harmoniq/fonts:ro 
        environment:
          # Tells Harmoniq where to find the YAML config inside the container
          - CONFIG_FILE_PATH=/app/config/config.yaml
          # Example of overriding a config value (LOG_LEVEL from YAML could be overridden here)
          # - LOG_LEVEL=DEBUG 
    ```

3.  **Run:**
    *   If building locally: `docker-compose build harmoniq` (or let `up --build` do it).
    *   Start the service: `docker-compose up -d`
    *   View logs: `docker-compose logs -f harmoniq`
    *   Stop: `docker-compose stop harmoniq`
    *   Stop and remove: `docker-compose down`

## Configuration Overview

Harmoniq uses a hierarchical configuration system:
1.  **Environment Variables (highest precedence):** Set directly in `docker-compose.yml` or loaded from the `.env` file. Ideal for secrets and quick overrides.
2.  **`config.yaml` (mounted into `/app/config/config.yaml`):** For structured and detailed configuration of features, playlists, periods, etc. See `config.yaml.example` for the full structure and options.
3.  **Internal Python Defaults (lowest precedence):** Defined in `src/harmoniq/config.py`.

**Key sections in `config.yaml`:**

*   `plex_url`, `plex_token`, `plex_music_library_names`
*   `timezone`
*   `lastfm_api_key`, `lastfm_user`
*   `features`: Toggle various functionalities like `enable_time_playlist`, `time_playlist.learn_from_history`, `time_playlist.use_sonic_adventure`, etc.
*   `playlists`: Define names, sizes, and specific parameters for "Harmoniq Flow" (`time_flow`), Last.fm playlists, etc. Includes refinement settings (min rating, recency, skips) and history integration parameters for "Harmoniq Flow".
*   `time_periods`: A list defining your named day parts for "Harmoniq Flow", their start hours, and optional mood/style overrides. Example:
    ```yaml
    time_periods:
      - name: "Morning"
        start_hour: 7
        # criteria: # Optional: overrides Harmoniq's internal defaults for "Morning"
        #   moods: ["Focused", "Productive"]
        #   styles: ["Instrumental", "Electronic"]
      - name: "EveningChill" # Custom name
        start_hour: 20
        criteria:
          moods: ["Relaxed", "Mellow"]
          styles: ["Jazz", "Acoustic"]
    ```
*   `cover_settings`: Configure playlist cover font, output path, and custom colors for different periods.
*   `log_level`.

Refer to `config.yaml.example` for detailed comments on all options.

## Usage

Once Harmoniq is running:
*   It initializes and schedules jobs based on your configuration.
*   The "Harmoniq Flow" playlist will update at the start of each period defined in `time_periods` (from `config.yaml`) or `TIME_PERIOD_SCHEDULE_RAW_ENV`.
*   Last.fm playlists update based on `run_interval_minutes`.
*   Check your Plex server for the generated playlists (e.g., "Harmoniq Flow," "Last.fm Discovery"). Playlist covers for "Harmoniq Flow" will update if enabled.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features and development phases.

## Contributing

Contributions are welcome! Whether it's bug reports, feature suggestions, or code contributions:

1.  Please check for existing issues before opening a new one.
2.  Feel free to open an issue to discuss proposed changes.
3.  Submit pull requests against the `main` (or `develop`) branch.

## License

This project is licensed under the [**CHOOSE A LICENSE - e.g., MIT License**]. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

*   Built with Python.
*   Key libraries: [python-plexapi](https://github.com/pkkid/python-plexapi), [Requests](https://requests.readthedocs.io/en/latest/), [schedule](https://schedule.readthedocs.io/en/stable/), [pytz](https://pythonhosted.org/pytz/).
*   Thanks to Last.fm for their public API and Plex for the rich metadata accessible via Sonic Analysis.