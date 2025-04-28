# src/harmoniq/main.py
import logging
# Import config variables
from . import config
# Import logger configured in log_config
from .log_config import logger
# Import Clients
from .plex_client import PlexClient
from .lastfm_client import LastfmClient
from .listenbrainz_client import ListenBrainzClient

def run_playlist_update_cycle():
    """
    Main logic loop that connects to services, fetches data,
    matches tracks, and updates Plex playlists.
    """
    logger.info("Starting playlist update cycle...")

    plex_client = None
    lastfm_client = None
    lb_client = None

    # --- Connect to Services ---
    try:
        plex_client = PlexClient()
        if config.ENABLE_LASTFM_RECS or config.ENABLE_LASTFM_CHARTS:
            # Only init if actually needed
            if config.LASTFM_API_KEY and config.LASTFM_USER:
                 lastfm_client = LastfmClient()
            else:
                 logger.warning("Last.fm client not initialized due to missing API Key or User.")

        if config.ENABLE_LISTENBRAINZ_RECS:
            # Init requires token (checked in config.py) and validates it
            if config.LISTENBRAINZ_USER_TOKEN: # Check should have been done in config, but double check
                 lb_client = ListenBrainzClient()
                 # If token validation failed during init, lb_client.api_user will be None
                 if lb_client and not lb_client.api_user:
                     logger.error("Disabling ListenBrainz features due to failed token validation during client init.")
                     lb_client = None # Ensure it's None if validation failed
    except ValueError as e: # Catch config value errors during client init
         logger.error(f"Configuration value error during client initialization: {e}. Aborting cycle.")
         return
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}. Aborting update cycle.")
        return

    # --- Get Plex Library ---
    music_library = None
    if plex_client:
        music_library = plex_client.get_music_library(config.PLEX_MUSIC_LIBRARY_NAME)
        if not music_library:
            logger.error(f"Could not access Plex music library '{config.PLEX_MUSIC_LIBRARY_NAME}'. Aborting update cycle.")
            return

    # --- Process Enabled Playlist Types ---

    # 1. Last.fm Recommendations
    if config.ENABLE_LISTENBRAINZ_RECS and lb_client and lb_client.api_user and music_library:
        logger.info("Processing ListenBrainz Recommendations...")
        recommendations = lb_client.get_recommendations(limit=config.PLAYLIST_SIZE_LISTENBRAINZ_RECS)
        if recommendations:
            logger.info(f"Fetched {len(recommendations)} recommendations from ListenBrainz. Matching in Plex...")

            matched_tracks_lb = []
            not_found_count_lb = 0
            for i, rec in enumerate(recommendations):
                logger.debug(f"Matching LB {i+1}/{len(recommendations)}: '{rec['artist']} - {rec['title']}'")
                plex_track = plex_client.find_track(music_library, rec['artist'], rec['title'])
                if plex_track:
                    matched_tracks_lb.append(plex_track)
                else:
                    logger.info(f"LB Track not found in Plex: {rec['artist']} - {rec['title']}")
                    not_found_count_lb += 1

            logger.info(f"ListenBrainz Matching complete. Found {len(matched_tracks_lb)} tracks in Plex. {not_found_count_lb} recommended tracks not found.")

            if matched_tracks_lb:
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_LISTENBRAINZ_RECS,
                    tracks_to_add=matched_tracks_lb,
                    music_library=music_library
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_LISTENBRAINZ_RECS}' playlist in Plex.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_LISTENBRAINZ_RECS}' playlist in Plex.")
            else:
                 logger.info("No matching tracks found in Plex for ListenBrainz recommendations. Playlist not created/updated.")
        else:
            logger.info("No recommendations received from ListenBrainz.")
    elif config.ENABLE_LISTENBRAINZ_RECS:
        logger.warning("Skipping ListenBrainz Recommendations: Client not available/validated or feature disabled.")


    # 2. Last.fm Recommendations (Optional/Fallback)
    if config.ENABLE_LASTFM_RECS and lastfm_client and music_library: # lastfm_client already checks for keys
        logger.info("Processing Last.fm Recommendations (Derived)...")
        recommendations_fm = lastfm_client.get_recommendations(limit=config.PLAYLIST_SIZE_LASTFM_RECS)
        if recommendations_fm:
            logger.info(f"Fetched {len(recommendations_fm)} derived recommendations. Matching in Plex...")

            matched_tracks_fm = []
            not_found_count_fm = 0
            for i, rec in enumerate(recommendations_fm):
                logger.debug(f"Matching FM-Rec {i+1}/{len(recommendations_fm)}: '{rec['artist']} - {rec['title']}'")
                plex_track = plex_client.find_track(music_library, rec['artist'], rec['title'])
                if plex_track:
                    matched_tracks_fm.append(plex_track)
                else:
                    logger.info(f"FM-Rec Track not found in Plex: {rec['artist']} - {rec['title']}")
                    not_found_count_fm += 1

            logger.info(f"Last.fm Rec Matching complete. Found {len(matched_tracks_fm)} tracks in Plex. {not_found_count_fm} recommended tracks not found.")

            if matched_tracks_fm:
                success = plex_client.update_playlist(
                    playlist_name=config.PLAYLIST_NAME_LASTFM_RECS,
                    tracks_to_add=matched_tracks_fm,
                    music_library=music_library
                )
                if success:
                     logger.info(f"Successfully updated '{config.PLAYLIST_NAME_LASTFM_RECS}' playlist in Plex.")
                else:
                     logger.error(f"Failed to update '{config.PLAYLIST_NAME_LASTFM_RECS}' playlist in Plex.")
            else:
                 logger.info("No matching tracks found in Plex for Last.fm recommendations. Playlist not created/updated.")
        else:
            logger.info("No derived recommendations generated from Last.fm.")
    elif config.ENABLE_LASTFM_RECS:
        logger.warning("Skipping Last.fm Recommendations: Client not available or feature disabled.")


    # 3. Last.fm Charts (Optional)
    if config.ENABLE_LASTFM_CHARTS and lastfm_client and music_library: # lastfm_client already checks for keys
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
         logger.warning("Skipping Last.fm Charts: Client not available or feature disabled.")


    # --- Add placeholders for other playlist types later ---
    # if config.ENABLE_TIME_PLAYLIST: ...

    logger.info("Playlist update cycle finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Phase 1 - Single Run)...")
    try:
        # Config loading happens on import, errors there will exit the script
        run_playlist_update_cycle()
    except Exception as e:
        # Catch errors happening during the cycle itself that weren't caught internally
        logger.exception(f"An unexpected error occurred during the main update cycle: {e}")
    finally:
        # This ensures the finished message is logged even if errors occur
        logger.info("Harmoniq service finished.")