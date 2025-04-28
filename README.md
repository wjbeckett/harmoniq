# Harmoniq

<!-- Add badges here (Build Status, License, Docker Hub pulls, etc.) -->
<!-- [![Build Status](...)](...) -->
<!-- [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) -->

Automated playlist generator for Plex (and eventually Jellyfin) using data from Last.fm. Keep your self-hosted music library fresh and discover new gems without lifting a finger!

## The Problem

Do you love your self-hosted music setup with Plex or Jellyfin but miss the automatically curated playlists like "Discover Weekly," "Your Mix," or "Top Charts" from streaming services? Manually creating playlists based on recommendations or charts can be tedious.

## The Solution

**Harmoniq** is a background service that connects to Last.fm and your Plex Media Server. It automatically generates and updates playlists in Plex based on various configurable criteria, bringing the convenience of streaming service playlists to your own library using available Last.fm data.

**(Note:** Initial attempts to integrate ListenBrainz recommendations and playlists were unsuccessful due to unavailable or non-functional public API endpoints. Support may be revisited if the ListenBrainz API situation changes.)

## Core Features

*   **Automatic Playlist Creation & Updates:** Runs periodically to keep playlists fresh.
*   **Last.fm Integration:**
    *   Creates playlists based on global chart data (Top Tracks).
    *   Creates *derived* recommendation playlists via similar artists logic (User Top Artists -> Similar Artists -> Top Tracks).
*   **(Planned) Time-Based Dynamic Playlists:** Configure a "Daily Flow" style playlist that changes content based on the time of day using Plex sonic data (moods, styles).
*   **(Planned) Custom Logic Integration:** Hooks for incorporating your own playlist generation scripts.
*   **Plex Support:** Directly interacts with your Plex Media Server library (supports multiple music libraries).
*   **(Planned) Jellyfin Support:** Future goal to support Jellyfin servers.
*   **Dockerized:** Easy deployment as a containerized background service.
*   **Configurable:** Fine-tune behavior using environment variables (API keys, playlist names, sizes, schedules, features).
*   **Missing Track Logging:** Reports source tracks that weren't found in your library (useful for manual acquisition or potential Lidarr integration).

## Prerequisites

*   **Docker:** Docker and Docker Compose installed on your system.
*   **Plex Media Server:** A running instance accessible via network from the Docker container.
*   **Plex Token:** Your [Plex Authentication Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
*   **Last.fm Account & API Key (Required):**
    *   Harmoniq relies on Last.fm for its current playlist generation features.
    *   API Key (Get one [here](https://www.last.fm/api/account/create))
    *   Your Last.fm Username

## Installation & Setup (Docker Compose Recommended)

1.  Create a `docker-compose.yml` file:

    ```yaml
    version: '3.7'

    services:
      harmoniq:
        image: harmoniq:latest # Or ghcr.io/your_username/harmoniq:latest, or use build context
        # build:
        #   context: ./src
        #   dockerfile: Dockerfile
        container_name: harmoniq
        restart: unless-stopped
        env_file:
          - .env
        # environment: # Overrides .env
        #   - PLEX_URL=...
        #   - LOG_LEVEL=DEBUG
        # volumes:
        #   - ./logs:/app/logs
    ```

2.  Create a `.env` file (copy `.env.example` and fill in your values):

    ```dotenv
    # .env - Harmoniq Configuration

    # --- Required Plex Configuration ---
    PLEX_URL=http://YOUR_PLEX_IP:32400
    PLEX_TOKEN=YOUR_PLEX_TOKEN
    PLEX_MUSIC_LIBRARY_NAMES=Music # Comma-separated list of EXACT Plex music library names

    # --- Scheduling & Timezone ---
    RUN_INTERVAL_MINUTES=1440 # Default: Daily
    TIMEZONE=UTC              # Optional: e.g., America/New_York

    # --- Last.fm Configuration (Required) ---
    LASTFM_API_KEY=YOUR_LASTFM_API_KEY
    LASTFM_USER=YOUR_LASTFM_USERNAME

    # --- Feature Flags ---
    ENABLE_LASTFM_RECS=true           # Uses derived recommendations (similar artists)
    ENABLE_LASTFM_CHARTS=true         # Good source for global charts
    ENABLE_TIME_PLAYLIST=false        # Planned feature

    # --- Playlist Naming ---
    PLAYLIST_NAME_LASTFM_RECS=Last.fm Discovery
    PLAYLIST_NAME_LASTFM_CHARTS=Last.fm Global Charts
    PLAYLIST_NAME_TIME=Daily Flow     # Planned feature

    # --- Playlist Sizing ---
    PLAYLIST_SIZE_LASTFM_RECS=30
    PLAYLIST_SIZE_LASTFM_CHARTS=50
    PLAYLIST_SIZE_TIME=40             # Planned feature

    # --- Logging ---
    LOG_LEVEL=INFO # Options: DEBUG, INFO, WARNING, ERROR
    ```

3.  **(Build Image Locally - if needed):**
    ```bash
    docker-compose build harmoniq
    ```

4.  **Run the container:**
    ```bash
    docker-compose up -d
    docker-compose logs -f harmoniq
    ```

## Configuration

Harmoniq is configured entirely through **environment variables** set in the `.env` file.

**Key Variables:**

| Variable                     | Description                                                                                           | Required?   | Default                     |
| :--------------------------- | :---------------------------------------------------------------------------------------------------- | :---------- | :-------------------------- |
| `PLEX_URL`                   | Full URL of your Plex Media Server (e.g., `http://192.168.1.100:32400`)                             | **Yes**     | -                           |
| `PLEX_TOKEN`                 | Your Plex authentication token.                                                                       | **Yes**     | -                           |
| `PLEX_MUSIC_LIBRARY_NAMES`   | Comma-separated list of the exact names of your Plex music libraries.                                 | **Yes**     | `Music`                     |
| `RUN_INTERVAL_MINUTES`       | How often (in minutes) to run the playlist update cycle.                                              | No          | `1440` (24 hours)           |
| `TIMEZONE`                   | Timezone for interpreting time-based playlists (e.g., `America/New_York`). [List TZ database names](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). | No          | `UTC`                       |
| `LASTFM_API_KEY`             | Your Last.fm API Key.                                                                                 | **Yes**     | -                           |
| `LASTFM_USER`                | Your Last.fm Username.                                                                                | **Yes**     | -                           |
| `ENABLE_LASTFM_RECS`         | Enable playlist based on Last.fm derived recommendations (`true`/`false`).                            | No          | `true`                      |
| `ENABLE_LASTFM_CHARTS`       | Enable playlist based on Last.fm global charts (`true`/`false`).                                      | No          | `true`                      |
| `ENABLE_TIME_PLAYLIST`       | Enable the dynamic time-based playlist (`true`/`false`).                                              | No          | `false` (Planned)           |
| `PLAYLIST_NAME_LASTFM_RECS`  | Set the name for the Last.fm recommendations playlist.                                                | No          | `Last.fm Discovery`         |
| `PLAYLIST_NAME_LASTFM_CHARTS`| Set the name for the Last.fm charts playlist.                                                         | No          | `Last.fm Global Charts`     |
| `PLAYLIST_NAME_TIME`         | Set the name for the time-based playlist.                                                             | No          | `Daily Flow` (Planned)      |
| `PLAYLIST_SIZE_LASTFM_RECS`  | Set the approximate number of tracks for the Last.fm recommendations playlist.                        | No          | `30`                        |
| `PLAYLIST_SIZE_LASTFM_CHARTS`| Set the approximate number of tracks for the Last.fm charts playlist.                                 | No          | `50`                        |
| `PLAYLIST_SIZE_TIME`         | Set the approximate number of tracks for the time-based playlist.                                     | No          | `40` (Planned)              |
| `LOG_LEVEL`                  | Set logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                          | No          | `INFO`                      |

**Security Note:** Treat your `PLEX_TOKEN` and `LASTFM_API_KEY` as sensitive secrets. Use the `.env` file or secure environment variable management.

## Usage

Once configured and running via Docker, Harmoniq operates in the background. It will wake up based on the `RUN_INTERVAL_MINUTES`, connect to Last.fm and Plex, fetch data, find matching tracks in your Plex library, and create or update the corresponding playlists within Plex.

Look for the playlists (e.g., "Last.fm Discovery", "Last.fm Global Charts") in your Plex client apps!

## Roadmap

See the [Roadmap.md](Roadmap.md) file for planned features, improvements, and development phases, including the time-based playlist, Jellyfin support, and more.

## Contributing

Contributions are welcome! Please check existing issues and feel free to open new ones or submit pull requests.

## License

This project is licensed under the [**CHOOSE A LICENSE - e.g., MIT License**]. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

*   Built with Python.
*   Relies heavily on the fantastic [python-plexapi](https://github.com/pkkid/python-plexapi) library.
*   Uses [Requests](https://requests.readthedocs.io/en/latest/) for API interactions.
*   Thanks to Last.fm for providing public APIs.