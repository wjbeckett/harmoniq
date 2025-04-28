# src/harmoniq/main.py
import logging
# Import config variables
from . import config
# Import logger configured in log_config
from .log_config import logger
# Import Clients
from .plex_client import PlexClient
from .lastfm_client import LastfmClient

def run_playlist_update_cycle():
    """
    Main logic loop that connects to services, fetches data,
    matches tracks, and updates Plex playlists.
    """
    logger.info("Starting playlist update cycle...")

    plex_client = None
    lastfm_client = None

    # --- Connect to Services ---
    try:
        plex_client = PlexClient()
        lastfm_client = LastfmClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}. Aborting update cycle.")
        return

    # --- Get Plex Library ---
    music_library = None
    if plex_client:
        music_library = plex_client.get_music_library()
        if not music_library:
            logger.error("Could not access Plex music library. Aborting update cycle.")
            return

    # --- Process Enabled Playlist Types ---

    # 1. Last.fm Recommendations
    if config.ENABLE_LASTFM_RECS and lastfm_client and lastfm_client.api_key and music_library:
        logger.info("Processing Last.fm Recommendations...")
        recommendations = lastfm_client.get_recommendations(limit=config.PLAYLIST_SIZE_LASTFM_RECS)
        if recommendations:
            logger.info(f"Fetched {len(recommendations)} recommendations. Matching in Plex...")

            matched_tracks = []
            not_found_count = 0
            for i, rec in enumerate(recommendations):
                logger.debug(f"Matching {i+1}/{len(recommendations)}: '{rec['artist']} - {rec['title']}'")
                plex_track = plex_client.find_track(music_library, rec['artist'], rec['title'])
                if plex_track:
                    matched_tracks.append(plex_track)
                else:
                    # Log missing tracks clearly at INFO level for visibility
                    logger.info(f"Track not found in Plex: {rec['artist']} - {rec['title']}")
                    not_found_count += 1

            logger.info(f"Matching complete. Found {len(matched_tracks)} tracks in Plex. {not_found_count} recommended tracks not found.")

            if matched_tracks:
                # Update the playlist using the plex_client method
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_LASTFM_RECS,
                    tracks_to_add=matched_tracks,
                    music_library=music_library # Pass library context
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_LASTFM_RECS}' playlist in Plex.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_LASTFM_RECS}' playlist in Plex.")
            else:
                 logger.info("No matching tracks found in Plex for Last.fm recommendations. Playlist not created/updated.")
                 # Optionally: Could delete the playlist if it exists and is now empty
                 # plex_client.delete_playlist(config.PLAYLIST_NAME_LASTFM_RECS) # Needs implementation

        else:
            logger.info("No recommendations received from Last.fm.")
    elif config.ENABLE_LASTFM_RECS:
        logger.warning("Skipping Last.fm Recommendations: Client/Library not available or feature disabled.")

    # 2. Last.fm Charts
    if config.ENABLE_LASTFM_CHARTS and lastfm_client and lastfm_client.api_key and music_library:
        logger.info("Processing Last.fm Charts...")
        chart_tracks_data = lastfm_client.get_chart_top_tracks(limit=config.PLAYLIST_SIZE_LASTFM_CHARTS)
        if chart_tracks_data:
            logger.info(f"Fetched {len(chart_tracks_data)} chart tracks. Matching in Plex...")

            matched_chart_tracks = []
            not_found_chart_count = 0
            for i, track_data in enumerate(chart_tracks_data):
                 logger.debug(f"Matching chart {i+1}/{len(chart_tracks_data)}: '{track_data['artist']} - {track_data['title']}'")
                 plex_track = plex_client.find_track(music_library, track_data['artist'], track_data['title'])
                 if plex_track:
                     matched_chart_tracks.append(plex_track)
                 else:
                     logger.info(f"Chart track not found in Plex: {track_data['artist']} - {track_data['title']}")
                     not_found_chart_count += 1

            logger.info(f"Matching complete for charts. Found {len(matched_chart_tracks)} tracks in Plex. {not_found_chart_count} chart tracks not found.")

            if matched_chart_tracks:
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_LASTFM_CHARTS,
                    tracks_to_add=matched_chart_tracks,
                    music_library=music_library
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_LASTFM_CHARTS}' playlist in Plex.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_LASTFM_CHARTS}' playlist in Plex.")
            else:
                 logger.info("No matching tracks found in Plex for Last.fm chart tracks. Playlist not created/updated.")

        else:
             logger.info("No chart tracks received from Last.fm.")

    elif config.ENABLE_LASTFM_CHARTS:
         logger.warning("Skipping Last.fm Charts: Client/Library not available or feature disabled.")


    # --- Add placeholders for other playlist types later ---
    # if config.ENABLE_LISTENBRAINZ_RECS: ...
    # if config.ENABLE_TIME_PLAYLIST: ...

    logger.info("Playlist update cycle finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Phase 1 - Single Run)...")
    try:
        run_playlist_update_cycle()
    except Exception as e:
        # Log any exception that occurs outside the main try/catch blocks in run_playlist_update_cycle
        logger.exception(f"An unexpected error occurred at the top level: {e}")
    logger.info("Harmoniq service finished.")