# Harmoniq

<!-- Add badges here (Build Status, License, Docker Hub pulls, etc.) -->
<!-- [![Build Status](...)](...) -->
<!-- [![License](...)](LICENSE) -->

Automated playlist generator for Plex (and eventually Jellyfin) using listening data from Last.fm and ListenBrainz. Keep your self-hosted music library fresh and discover new gems without lifting a finger!

## The Problem

Do you love your self-hosted music setup with Plex or Jellyfin but miss the automatically curated playlists like "Discover Weekly" or "Daily Mix" from streaming services? Manually creating playlists based on recommendations or charts can be tedious.

## The Solution

**Harmoniq** is a background service that connects to your listening history services (Last.fm, ListenBrainz) and your Plex Media Server. It automatically generates and updates playlists based on various configurable criteria, bringing the convenience of streaming service playlists to your own library.

## Core Features

*   **Automatic Playlist Creation & Updates:** Runs periodically to keep playlists fresh.
*   **ListenBrainz Integration (Primary):**
    *   Creates playlists from your personalized track recommendations (requires ListenBrainz token).
*   **Last.fm Integration (Optional):**
    *   Creates playlists based on global chart data (requires Last.fm API key/user).
    *   (Optional) Creates derived recommendation playlists via similar artists (if enabled).
*   **(Planned) Time-Based Dynamic Playlists:** Configure a "Daily Flow" style playlist that changes content based on the time of day (e.g., chill morning music, energetic afternoon tunes).
*   **(Planned) Custom Logic Integration:** Hooks for incorporating your own playlist generation scripts.
*   **Plex Support:** Directly interacts with your Plex Media Server library.
*   **(Planned) Jellyfin Support:** Future goal to support Jellyfin servers.
*   **Dockerized:** Easy deployment as a containerized background service.
*   **Configurable:** Fine-tune behavior using environment variables (API keys, playlist names, sizes, schedules, features).
*   **Missing Track Logging:** Reports recommended tracks that weren't found in your library (useful for manual acquisition or potential Lidarr integration).

## Prerequisites

*   **Docker:** Docker and Docker Compose installed on your system.
*   **Plex Media Server:** A running instance accessible via network from the Docker container.
*   **Plex Token:** Your [Plex Authentication Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
*   **ListenBrainz Account & Token (Recommended):**
    *   Required for personalized recommendations (`ENABLE_LISTENBRAINZ_RECS=true`).
    *   Your ListenBrainz User Token (Find in your profile settings on listenbrainz.org).
*   **Last.fm Account (Optional):**
    *   Required for global charts (`ENABLE_LASTFM_CHARTS=true`) or derived recommendations (`ENABLE_LASTFM_RECS=true`).
    *   API Key (Get one [here](https://www.last.fm/api/account/create))
    *   Your Last.fm Username

## Installation & Setup (Docker Compose Recommended)

1.  Create a `docker-compose.yml` file:

    ```yaml
    version: '3.7'

    services:
      Harmoniq:
        # Replace 'your_username/Harmoniq:latest' with the final image name/source if building locally or pulling from a registry
        image: Harmoniq:latest # Or e.g., ghcr.io/your_username/Harmoniq:latest
        container_name: Harmoniq
        restart: unless-stopped
        environment:
          # --- Required Plex Configuration ---
          - PLEX_URL=http://YOUR_PLEX_IP:32400 # Replace with your Plex server URL
          - PLEX_TOKEN=YOUR_PLEX_TOKEN         # Replace with your Plex token
          - PLEX_MUSIC_LIBRARY_NAME=Music     # Replace with the EXACT name of your Plex music library

          # --- Scheduling & Timezone ---
          - RUN_INTERVAL_MINUTES=1440          # Update playlists daily (1440), hourly (60), etc.
          - TIMEZONE=UTC                       # Optional: e.g., America/New_York, Europe/London. Defaults to UTC.

          # --- Last.fm Configuration (Required for Last.fm features) ---
          - LASTFM_API_KEY=YOUR_LASTFM_API_KEY # Replace with your Last.fm API Key
          - LASTFM_USER=YOUR_LASTFM_USERNAME   # Replace with your Last.fm Username

          # --- ListenBrainz Configuration (Required for ListenBrainz features) ---
          # - LISTENBRAINZ_USER_TOKEN=YOUR_LISTENBRAINZ_TOKEN # Uncomment and replace when implemented

          # --- Feature Flags (Enable/Disable specific playlist types) ---
          - ENABLE_LASTFM_RECS=true           # Enable Last.fm user recommendations playlist
          - ENABLE_LASTFM_CHARTS=true         # Enable Last.fm global charts playlist
          - ENABLE_LISTENBRAINZ_RECS=false    # Enable ListenBrainz recommendations (when implemented)
          - ENABLE_TIME_PLAYLIST=false        # Enable the time-based dynamic playlist (when implemented)
          # - ENABLE_CUSTOM_1=false           # Enable custom playlist logic (when implemented)

          # --- Playlist Naming ---
          - PLAYLIST_NAME_LASTFM_RECS=Last.fm Discovery
          - PLAYLIST_NAME_LASTFM_CHARTS=Last.fm Global Charts
          - PLAYLIST_NAME_LISTENBRAINZ_RECS=ListenBrainz Discovery # (when implemented)
          - PLAYLIST_NAME_TIME=Daily Flow                          # (when implemented)
          # - PLAYLIST_NAME_CUSTOM_1=My Custom Playlist            # (when implemented)

          # --- Playlist Sizing ---
          - PLAYLIST_SIZE_LASTFM_RECS=30
          - PLAYLIST_SIZE_LASTFM_CHARTS=50
          - PLAYLIST_SIZE_LISTENBRAINZ_RECS=30                     # (when implemented)
          - PLAYLIST_SIZE_TIME=40                                  # (when implemented)
          # - PLAYLIST_SIZE_CUSTOM_1=25                            # (when implemented)

          # --- Time Playlist Configuration (Example - when implemented) ---
          # - TIME_WINDOWS="00:00-06:00:genres=Ambient,Sleep;06:00-11:00:genres=Chillout,Acoustic;11:00-17:00:tags=upbeat,rock;17:00-24:00:genres=Jazz,Classical"

          # --- Logging ---
          # - LOG_LEVEL=INFO # Optional: Set log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.

        # --- Optional: Volumes (Uncomment if needed later for logs or config files) ---
        # volumes:
        #   - ./logs:/app/logs # Example: Mount a volume for persistent logs if needed
        #   - ./custom_scripts:/app/custom_scripts # Example: Mount custom scripts
    ```

2.  **(Build Image Locally - if needed):** If you cloned the repository, navigate to the project directory and run:
    ```bash
    docker build -t Harmoniq:latest .
    ```

3.  **Run the container:**
    ```bash
    docker-compose up -d
    ```

## Configuration

Harmoniq is configured entirely through **environment variables**, as shown in the `docker-compose.yml` example above.

**Key Variables:**

| Variable                       | Description                                                                                             | Required?        | Default                |
| :----------------------------- | :------------------------------------------------------------------------------------------------------ | :--------------- | :--------------------- |
| `PLEX_URL`                     | Full URL of your Plex Media Server (e.g., `http://192.168.1.100:32400`)                                | **Yes**          | -                      |
| `PLEX_TOKEN`                   | Your Plex authentication token.                                                                         | **Yes**          | -                      |
| `PLEX_MUSIC_LIBRARY_NAME`      | The exact name of the music library in Plex to use.                                                     | **Yes**          | `Music`                |
| `RUN_INTERVAL_MINUTES`         | How often (in minutes) to run the playlist update cycle.                                                | No               | `1440` (24 hours)      |
| `TIMEZONE`                     | Timezone for interpreting time-based playlists (e.g., `America/New_York`). [List TZ database names](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). | No               | `UTC`                  |
| `LASTFM_API_KEY`               | Your Last.fm API Key.                                                                                   | If Last.fm used  | -                      |
| `LASTFM_USER`                  | Your Last.fm Username.                                                                                  | If Last.fm used  | -                      |
| `LISTENBRAINZ_USER_TOKEN`      | Your ListenBrainz User Token.                                                                           | If LB used       | -                      |
| `ENABLE_LASTFM_RECS`           | Enable playlist based on Last.fm user recommendations (`true`/`false`).                                 | No               | `true`                 |
| `ENABLE_LASTFM_CHARTS`         | Enable playlist based on Last.fm global charts (`true`/`false`).                                        | No               | `true`                 |
| `ENABLE_LISTENBRAINZ_RECS`     | Enable playlist based on ListenBrainz recommendations (`true`/`false`).                                 | No               | `false` (Planned)      |
| `ENABLE_TIME_PLAYLIST`         | Enable the dynamic time-based playlist (`true`/`false`).                                                | No               | `false` (Planned)      |
| `PLAYLIST_NAME_*`              | Set the name for each generated playlist in Plex (e.g., `PLAYLIST_NAME_LASTFM_RECS`).                   | No               | See examples           |
| `PLAYLIST_SIZE_*`              | Set the approximate number of tracks for each playlist (e.g., `PLAYLIST_SIZE_LASTFM_RECS`).               | No               | See examples           |
| `TIME_WINDOWS`                 | Defines windows and criteria for the time playlist (Format TBD, see example).                           | If Time Playlist | - (Planned)            |
| `LOG_LEVEL`                    | Set logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                            | No               | `INFO`                 |

**Security Note:** Treat your `PLEX_TOKEN`, `LASTFM_API_KEY`, and `LISTENBRAINZ_USER_TOKEN` as sensitive secrets. Do not commit them directly into version control. Use environment variables as intended.

## Usage

Once configured and running via Docker, Harmoniq operates in the background. It will wake up based on the `RUN_INTERVAL_MINUTES`, connect to the configured services, fetch data, find matching tracks in your Plex library, and create or update the corresponding playlists directly within Plex.

Simply look for the playlists (with names matching your `PLAYLIST_NAME_*` configuration) in your Plex client apps!

## Roadmap

See the [Roadmap.md](Roadmap.md) file for planned features, improvements, and development phases, including ListenBrainz support, the time-based playlist, Jellyfin support, and more.

## Contributing

Contributions are welcome! Whether it's bug reports, feature suggestions, or code contributions:

1.  Please check for existing issues before opening a new one.
2.  Feel free to open an issue to discuss proposed changes.
3.  Submit pull requests against the `main` (or `develop`) branch.
4.  (Optional: Add more specific contribution guidelines later, potentially in a `CONTRIBUTING.md` file).

## License

This project is licensed under the [**CHOOSE A LICENSE - e.g., MIT License**]. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

*   Built with Python.
*   Relies heavily on the fantastic [python-plexapi](https://github.com/pkkid/python-plexapi) library.
*   Uses [Requests](https://requests.readthedocs.io/en/latest/) for API interactions.
*   Uses [schedule](https://schedule.readthedocs.io/en/stable/) or APScheduler for internal job scheduling.
*   Thanks to Last.fm and ListenBrainz for providing public APIs.