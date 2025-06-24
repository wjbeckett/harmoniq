# src/harmoniq/main.py
import os
import logging
from datetime import datetime
import pytz
from . import config
from .log_config import logger
from .plex_client import PlexClient
from .lastfm_client import LastfmClient
from .image_utils import generate_playlist_cover
from .stats_tracker import get_stats_tracker


# --- Helper Function to get current active period details ---
def get_active_period_details() -> dict | None:
    if not config.SCHEDULED_PERIODS:
        logger.debug("No scheduled periods configured or parsed.")
        return None
    try:
        tz = pytz.timezone(config.TIMEZONE)
        now_local = datetime.now(tz)
        current_hour = now_local.hour
        logger.debug(
            f"Current local time for period check: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z%z')}, Current Hour: {current_hour}"
        )
    except Exception as e:
        logger.error(
            f"Error getting current time with timezone '{config.TIMEZONE}': {e}. Defaulting to UTC."
        )
        now_local = datetime.now(pytz.utc)
        current_hour = now_local.hour

    active_period_candidate = None

    # SCHEDULED_PERIODS is sorted by start_hour in config.py
    # Find the latest period that has started
    for p_details in config.SCHEDULED_PERIODS:
        if p_details["start_hour"] <= current_hour:
            active_period_candidate = p_details
        elif active_period_candidate is None and p_details["start_hour"] > current_hour:
            # If current hour is before the first scheduled period, use the last period of the day (wraparound)
            active_period_candidate = config.SCHEDULED_PERIODS[-1]
            break
        elif p_details["start_hour"] > current_hour:
            # We've passed current_hour, so the previous candidate was correct
            break

    # If loop finishes and active_period_candidate is still None (e.g., empty SCHEDULED_PERIODS after all),
    # or if current hour is before the first period in a non-empty list.
    if active_period_candidate is None and config.SCHEDULED_PERIODS:
        active_period_candidate = config.SCHEDULED_PERIODS[
            -1
        ]  # Default to last for wraparound

    if active_period_candidate:
        # Calculate the set of hours for this active period
        period_name = active_period_candidate["name"]
        start_h = active_period_candidate["start_hour"]

        current_period_index = -1
        for i, p_conf in enumerate(config.SCHEDULED_PERIODS):
            if p_conf["name"] == period_name:
                current_period_index = i
                break

        end_h_exclusive = 24  # Default to end of day
        if current_period_index != -1:  # Should always be found
            if current_period_index + 1 < len(config.SCHEDULED_PERIODS):
                end_h_exclusive = config.SCHEDULED_PERIODS[current_period_index + 1][
                    "start_hour"
                ]
            else:  # This is the last defined period, so it runs until the first period of the next day
                end_h_exclusive = config.SCHEDULED_PERIODS[0]["start_hour"]
                # If end_h_exclusive is <= start_h, it means it wraps around midnight.
                # If it wraps, hours are start_h..23 and 0..end_h_exclusive-1
                # If it doesn't wrap past first period (e.g. last period 22:00, first is 05:00), it effectively means up to 24:00 (exclusive)
                if end_h_exclusive > start_h:
                    end_h_exclusive = 24  # Not wrapping past midnight to next day's first period start time

        active_hours_set = set()
        if (
            start_h < end_h_exclusive
        ):  # Normal day segment or ends at midnight (represented as 24)
            for h_loop in range(start_h, end_h_exclusive):
                active_hours_set.add(h_loop)
        else:  # Overnight segment (e.g. 22:00 start, next period starts at 05:00 next day)
            for h_loop in range(start_h, 24):
                active_hours_set.add(h_loop)
            for h_loop in range(0, end_h_exclusive):
                active_hours_set.add(h_loop)

        # Create a copy to add 'hours_set' to, to avoid modifying the global config.SCHEDULED_PERIODS items
        return_period_details = active_period_candidate.copy()
        return_period_details["hours_set"] = active_hours_set
        logger.info(
            f"Active period: '{period_name}' (Starts {start_h:02d}:00). Effective Hours: {sorted(list(active_hours_set))}. Criteria: {return_period_details['criteria']}"
        )
        return return_period_details
    else:
        logger.warning(
            f"Could not determine active period for current hour: {current_hour}. Using fallback 'DefaultVibe'."
        )
        return {
            "name": "DefaultVibe",
            "start_hour": current_hour,
            "criteria": config.DEFAULT_PERIOD_VIBES.get(
                "DefaultVibe", {"moods": [], "styles": []}
            ),
            "hours_set": set(range(24)),
        }


# --- Function specifically for Harmoniq Flow update ---
def run_harmoniq_flow_update(
    plex_client: PlexClient,
    valid_music_libraries: list,
    target_library,
    active_period_details: dict | None,
):
    """Handles the update logic for the Time-Based 'Harmoniq Flow' Playlist."""
    stats_tracker = get_stats_tracker()
    if not (config.ENABLE_TIME_PLAYLIST and plex_client and valid_music_libraries):
        logger.info(
            "Skipping Harmoniq Flow: Feature disabled or Plex client/libraries not available."
        )
        return

    if not active_period_details:
        active_period_details = get_active_period_details()

    if active_period_details and "hours_set" in active_period_details:
        period_name = active_period_details["name"]
        # These are the BASE target moods/styles from config (default or user TP_DEFINE_ override)
        # The generate_harmoniq_flow_playlist method will handle learning/augmentation internally
        base_target_moods = active_period_details["criteria"]["moods"]
        base_target_styles = active_period_details["criteria"]["styles"]
        period_hours_set = active_period_details["hours_set"]

        stats_tracker.record_period_switch(period_name)

        # The main processing, including vibe learning, is now inside generate_harmoniq_flow_playlist
        logger.info(
            f"Processing Harmoniq Flow for period '{period_name}' using base criteria (learning will happen in PlexClient)..."
        )
        # logger.info(f"Base Period Criteria: Moods={base_target_moods}, Styles/Genres={base_target_styles}, Effective Hours={sorted(list(period_hours_set))}")

        time_based_tracks = plex_client.generate_harmoniq_flow_playlist(
            libraries=valid_music_libraries,
            active_period_name=period_name,
            base_target_moods=base_target_moods,  # Pass BASE moods
            base_target_styles=base_target_styles,  # Pass BASE styles
            period_active_hours=period_hours_set,
            playlist_target_size=config.PLAYLIST_SIZE_TIME,
        )

        if time_based_tracks:
            logger.info(
                f"Generated {len(time_based_tracks)} tracks for the '{period_name}' period for playlist update."
            )
            playlist_updated = plex_client.update_playlist(
                config.PLAYLIST_NAME_TIME,
                time_based_tracks,
                target_library,
                active_period_name=period_name,
            )

            if playlist_updated:
                logger.info(
                    f"Successfully updated '{config.PLAYLIST_NAME_TIME}' for '{period_name}'."
                )
                stats_tracker.record_playlist_update(
                    period_name, len(time_based_tracks)
                )
                if config.ENABLE_PLAYLIST_COVERS:
                    logger.info("Attempting to generate and upload playlist cover...")
                    cover_image_path = generate_playlist_cover(
                        playlist_title=config.PLAYLIST_NAME_TIME,
                        period_name=period_name,
                        active_moods=base_target_moods,
                        active_styles=base_target_styles,
                    )

                    if cover_image_path and os.path.exists(
                        cover_image_path
                    ):  # os is available here
                        try:
                            plex_playlist_obj = plex_client.plex.playlist(
                                config.PLAYLIST_NAME_TIME
                            )
                            if plex_playlist_obj:
                                plex_client.upload_playlist_cover(
                                    plex_playlist_obj, cover_image_path
                                )
                            else:
                                logger.warning(
                                    f"Could not retrieve playlist '{config.PLAYLIST_NAME_TIME}' to upload cover."
                                )
                        except Exception as e_cover_upload:
                            # --- MODIFIED LOGGING HERE ---
                            logger.error(
                                f"Caught exception during cover retrieval/upload. Error: {e_cover_upload}"
                            )
                            logger.exception(
                                "Full traceback for cover upload failure:"
                            )  # This will print the traceback
                            # --- END MODIFIED LOGGING ---
                        finally:
                            # ... (finally block with os.path.exists and os.remove - this part seems to work) ...
                            logger.debug(
                                f"DEBUG_OS: Type of 'os' in finally: {type(os)}"
                            )
                            logger.debug(
                                f"DEBUG_OS: os.path.exists available: {hasattr(os, 'path') and hasattr(os.path, 'exists')}"
                            )
                            if os.path.exists(config.COVER_OUTPUT_PATH):
                                try:
                                    os.remove(config.COVER_OUTPUT_PATH)
                                    logger.debug(
                                        f"Temp cover '{config.COVER_OUTPUT_PATH}' removed."
                                    )
                                except OSError as e_remove:
                                    logger.warning(
                                        f"Could not remove temp cover '{config.COVER_OUTPUT_PATH}': {e_remove}"
                                    )
                            else:
                                logger.debug(
                                    f"DEBUG_OS: Temp cover file {config.COVER_OUTPUT_PATH} does not exist for removal (or os.path.exists failed)."
                                )
            else:
                logger.error(
                    f"Failed to update '{config.PLAYLIST_NAME_TIME}' for '{period_name}', cover not generated."
                )
        else:
            logger.info(
                f"No tracks generated for '{period_name}'. '{config.PLAYLIST_NAME_TIME}' not updated."
            )
    elif active_period_details and "hours_set" not in active_period_details:
        logger.error(
            f"Active period details for '{active_period_details.get('name')}' missing 'hours_set'."
        )
    else:
        logger.info("No active time period. 'Harmoniq Flow' playlist not updated.")


# --- Function to run the Library Grower cycle ---
def run_library_grower_cycle():
    """
    Main Library Grower cycle: Fetch top artists from Last.fm, find similar artists,
    get their albums, filter by type, and add suitable ones to Lidarr.
    """
    if not config.ENABLE_LIBRARY_GROWER:
        logger.info("Library Grower is disabled. Skipping cycle.")
        return

    stats_tracker = get_stats_tracker()

    logger.info("Starting Library Grower cycle...")

    # Initialize clients
    try:
        from .lastfm_client import LastfmClient
        from .lidarr_client import LidarrClient
        from .musicbrainz_client import MusicBrainzClient

        # Check required config
        if not all([config.LASTFM_API_KEY, config.LASTFM_USER]):
            logger.error(
                "Library Grower: Last.fm API key or username not configured. Aborting."
            )
            return

        if not all(
            [config.LIDARR_URL, config.LIDARR_API_KEY, config.LIDARR_ROOT_FOLDER_PATH]
        ):
            logger.error("Library Grower: Lidarr configuration incomplete. Aborting.")
            return

        # Initialize clients
        lastfm_client = LastfmClient(config.LASTFM_API_KEY, config.LASTFM_USER)
        lidarr_client = LidarrClient(config.LIDARR_URL, config.LIDARR_API_KEY)
        musicbrainz_client = (
            MusicBrainzClient()
            if config.LIBRARY_GROWER_PREFER_MUSICBRAINZ_FILTER
            else None
        )

        # Test connections
        if not lidarr_client.test_connection():
            logger.error("Library Grower: Failed to connect to Lidarr. Aborting.")
            return

        logger.info("Library Grower: All clients initialized successfully.")

    except Exception as e:
        logger.error(f"Library Grower: Failed to initialize clients: {e}")
        return

    # Statistics tracking
    stats = {
        "top_artists_fetched": 0,
        "similar_artists_found": 0,
        "albums_considered": 0,
        "albums_filtered_by_tags": 0,
        "albums_filtered_by_mb_type": 0,
        "albums_already_in_lidarr": 0,
        "albums_added_to_lidarr": 0,
        "albums_failed_to_add": 0,
    }

    try:
        # Step 1: Get user's top artists from Last.fm
        logger.info(
            f"Fetching top {config.LIBRARY_GROWER_TOP_ARTISTS_COUNT} artists for user '{config.LASTFM_USER}' (period: {config.LIBRARY_GROWER_TOP_ARTISTS_PERIOD})"
        )

        top_artists = lastfm_client.get_user_top_artists(
            period=config.LIBRARY_GROWER_TOP_ARTISTS_PERIOD,
            limit=config.LIBRARY_GROWER_TOP_ARTISTS_COUNT,
        )

        if not top_artists:
            logger.warning("Library Grower: No top artists found. Aborting cycle.")
            return

        stats["top_artists_fetched"] = len(top_artists)
        logger.info(f"Library Grower: Found {len(top_artists)} top artists")

        # Step 2: Get similar artists for each top artist
        all_similar_artists = set()  # Use set to avoid duplicates

        for i, top_artist in enumerate(top_artists):
            artist_name = top_artist.get("name", "")
            artist_mbid = top_artist.get("mbid", "")
            logger.debug(
                f"Processing top artist {i+1}/{len(top_artists)}: {artist_name}"
            )

            # Use MBID if available, otherwise use name
            similar_artists = lastfm_client.get_similar_artists(
                artist_name=artist_name if not artist_mbid else None,
                artist_mbid=artist_mbid if artist_mbid else None,
                limit=config.LIBRARY_GROWER_SIMILAR_ARTISTS_PER_TOP_ARTIST,
            )

            if similar_artists:
                for similar_artist in similar_artists:
                    similar_name = similar_artist.get("name", "").strip()
                    similar_mbid = similar_artist.get("mbid", "").strip()
                    if similar_name:
                        # Store both name and MBID for later use
                        all_similar_artists.add((similar_name, similar_mbid))

        stats["similar_artists_found"] = len(all_similar_artists)
        logger.info(
            f"Library Grower: Found {len(all_similar_artists)} unique similar artists"
        )

        if not all_similar_artists:
            logger.warning("Library Grower: No similar artists found. Aborting cycle.")
            return

        # Step 3: Get top albums for each similar artist
        candidate_albums = []

        for i, (artist_name, artist_mbid) in enumerate(all_similar_artists):
            logger.debug(
                f"Getting albums for similar artist {i+1}/{len(all_similar_artists)}: {artist_name}"
            )

            # Use MBID if available, otherwise use name
            artist_albums = lastfm_client.get_artist_top_albums(
                artist_name=artist_name if not artist_mbid else None,
                artist_mbid=artist_mbid if artist_mbid else None,
                limit=config.LIBRARY_GROWER_ALBUMS_PER_SIMILAR_ARTIST,
            )

            if artist_albums:
                for album in artist_albums:
                    album_name = album.get("name", "").strip()
                    album_mbid = album.get("mbid", "").strip()
                    if album_name:
                        candidate_albums.append(
                            {
                                "artist_name": artist_name,
                                "album_name": album_name,
                                "album_mbid": album_mbid,
                                "lastfm_data": album,
                            }
                        )

        stats["albums_considered"] = len(candidate_albums)
        logger.info(f"Library Grower: Found {len(candidate_albums)} candidate albums")

        if not candidate_albums:
            logger.warning("Library Grower: No candidate albums found. Aborting cycle.")
            return

        # Step 4: Filter and process albums
        albums_to_add = []

        for i, album_info in enumerate(candidate_albums):
            artist_name = album_info["artist_name"]
            album_name = album_info["album_name"]
            album_mbid = album_info["album_mbid"]
            lastfm_album_data = album_info["lastfm_data"]

            logger.debug(
                f"Processing album {i+1}/{len(candidate_albums)}: '{album_name}' by {artist_name}"
            )

            # Get detailed album info from Last.fm (including MBID and tags)
            # Use MBID if we have it, otherwise use artist/album names
            if album_mbid:
                detailed_album_info = lastfm_client.get_album_info(
                    artist_name=artist_name, album_name=album_name, mbid=album_mbid
                )
            else:
                detailed_album_info = lastfm_client.get_album_info(
                    artist_name=artist_name, album_name=album_name
                )

            if not detailed_album_info:
                logger.debug(
                    f"Could not get detailed info for '{album_name}' by {artist_name}"
                )
                continue

            # Extract MBID and tags from detailed info
            final_album_mbid = detailed_album_info.get("mbid", "").strip()
            if not final_album_mbid:
                final_album_mbid = album_mbid  # Fall back to the one from top albums

            # Extract tags - they're nested under tags.tag
            album_tags = []
            tags_data = detailed_album_info.get("tags", {})
            if isinstance(tags_data, dict) and "tag" in tags_data:
                raw_tags = tags_data["tag"]
                if isinstance(raw_tags, list):
                    album_tags = raw_tags
                elif isinstance(raw_tags, dict):
                    album_tags = [raw_tags]  # Single tag case

            # Filter by Last.fm tags first (basic filtering)
            if album_tags and config.LIBRARY_GROWER_EXCLUDE_ALBUM_TAGS:
                tag_names = [
                    tag.get("name", "").lower()
                    for tag in album_tags
                    if isinstance(tag, dict)
                ]
                excluded_tags = [
                    tag.lower().strip()
                    for tag in config.LIBRARY_GROWER_EXCLUDE_ALBUM_TAGS
                ]

                if any(excluded_tag in tag_names for excluded_tag in excluded_tags):
                    logger.debug(
                        f"Album '{album_name}' filtered out by Last.fm tags: {tag_names}"
                    )
                    stats["albums_filtered_by_tags"] += 1
                    continue

            # Filter by MusicBrainz type if enabled and MBID available
            if musicbrainz_client and final_album_mbid:
                try:
                    # Convert Release MBID to Release Group MBID if needed
                    release_group_mbid = final_album_mbid
                    if len(final_album_mbid) == 36:  # Standard MBID format
                        # Try to get release group MBID (in case we got a release MBID)
                        rg_mbid = (
                            musicbrainz_client.get_release_group_mbid_from_album_mbid(
                                final_album_mbid
                            )
                        )
                        if rg_mbid:
                            release_group_mbid = rg_mbid

                    # Get album type information
                    album_type_info = (
                        musicbrainz_client.get_album_type_by_release_group_mbid(
                            release_group_mbid
                        )
                    )

                    if album_type_info:
                        if not album_type_info.get("is_studio_album", False):
                            logger.debug(
                                f"Album '{album_name}' filtered out by MusicBrainz type: "
                                f"primary={album_type_info.get('primary_type')}, "
                                f"secondary={album_type_info.get('secondary_types')}"
                            )
                            stats["albums_filtered_by_mb_type"] += 1
                            continue
                        else:
                            logger.debug(
                                f"Album '{album_name}' passed MusicBrainz filter as studio album"
                            )
                    else:
                        logger.debug(
                            f"Could not get MusicBrainz type info for '{album_name}' (MBID: {release_group_mbid})"
                        )
                        # Continue without MusicBrainz filtering if we can't get the info

                except Exception as e:
                    logger.warning(
                        f"Error checking MusicBrainz type for '{album_name}': {e}"
                    )
                    # Continue without MusicBrainz filtering on error

            # Check if album already exists in Lidarr
            if final_album_mbid:
                try:
                    if lidarr_client.album_exists_in_library(final_album_mbid):
                        logger.debug(f"Album '{album_name}' already exists in Lidarr")
                        stats["albums_already_in_lidarr"] += 1
                        continue
                except Exception as e:
                    logger.warning(f"Error checking if album exists in Lidarr: {e}")
                    # Continue to try adding it

            # Album passed all filters - add to list for Lidarr
            albums_to_add.append(
                {
                    "artist_name": artist_name,
                    "album_name": album_name,
                    "mbid": final_album_mbid,
                    "detailed_info": detailed_album_info,
                }
            )

        logger.info(
            f"Library Grower: {len(albums_to_add)} albums passed filtering and will be added to Lidarr"
        )

        # Step 5: Add albums to Lidarr
        for album_to_add in albums_to_add:
            artist_name = album_to_add["artist_name"]
            album_name = album_to_add["album_name"]
            album_mbid = album_to_add["mbid"]

            if not album_mbid:
                logger.warning(
                    f"No MBID for '{album_name}' by {artist_name}, skipping Lidarr add"
                )
                stats["albums_failed_to_add"] += 1
                continue

            try:
                logger.info(
                    f"Adding to Lidarr: '{album_name}' by {artist_name} (MBID: {album_mbid})"
                )

                result = lidarr_client.add_album_by_mbid(
                    release_group_mbid=album_mbid,
                    root_folder_path=config.LIDARR_ROOT_FOLDER_PATH,
                    quality_profile_id=config.LIDARR_QUALITY_PROFILE_ID,
                    metadata_profile_id=config.LIDARR_METADATA_PROFILE_ID,
                    monitored=config.LIDARR_ADD_ALBUM_MONITORED,
                    search_on_add=config.LIDARR_SEARCH_FOR_ALBUM_ON_ADD,
                )

                if result:
                    logger.info(
                        f"Successfully added '{album_name}' by {artist_name} to Lidarr"
                    )
                    stats["albums_added_to_lidarr"] += 1
                else:
                    logger.warning(
                        f"Failed to add '{album_name}' by {artist_name} to Lidarr"
                    )
                    stats["albums_failed_to_add"] += 1

            except Exception as e:
                logger.error(
                    f"Error adding '{album_name}' by {artist_name} to Lidarr: {e}"
                )
                stats["albums_failed_to_add"] += 1

        # Log final statistics
        logger.info("Library Grower cycle completed. Statistics:")
        logger.info(f"  Top artists fetched: {stats['top_artists_fetched']}")
        logger.info(f"  Similar artists found: {stats['similar_artists_found']}")
        logger.info(f"  Albums considered: {stats['albums_considered']}")
        logger.info(f"  Albums filtered by tags: {stats['albums_filtered_by_tags']}")
        logger.info(
            f"  Albums filtered by MusicBrainz type: {stats['albums_filtered_by_mb_type']}"
        )
        logger.info(f"  Albums already in Lidarr: {stats['albums_already_in_lidarr']}")
        logger.info(
            f"  Albums successfully added to Lidarr: {stats['albums_added_to_lidarr']}"
        )
        logger.info(f"  Albums failed to add: {stats['albums_failed_to_add']}")

        stats_tracker.record_library_grower_activity(
            albums_added=stats["albums_added_to_lidarr"],
            artists_processed=stats["similar_artists_found"],
        )

    except Exception as e:
        logger.exception(f"Library Grower: Unexpected error during cycle: {e}")


# --- Combined function for single run (useful for if __name__ == "__main__") ---
def run_all_updates_once():
    logger.info("Starting all playlist update cycles (single run)...")
    plex_client = None
    lastfm_client = None
    try:
        plex_client = PlexClient()
    except Exception as e:
        logger.error(
            f"Failed during client initialization for single run: {e}. Aborting."
        )
        return

    valid_music_libraries = []
    if plex_client:
        for name in config.PLEX_MUSIC_LIBRARY_NAMES:
            lib = plex_client.get_music_library(name)
            if lib:
                valid_music_libraries.append(lib)
        if not valid_music_libraries:
            logger.error("No valid Plex music libraries for single run. Aborting.")
            return
    else:
        logger.error("Plex client not initialized for single run. Aborting.")
        return

    target_library = valid_music_libraries[0]

    # For a single manual run, get the current active period and run flow update
    active_period = get_active_period_details()
    if active_period:
        run_harmoniq_flow_update(
            plex_client, valid_music_libraries, target_library, active_period
        )  # Pass active_period
    else:
        logger.warning(
            "Manual run: No active period identified, skipping Harmoniq Flow update."
        )

    logger.info("All playlist update cycles (single run) finished.")


if __name__ == "__main__":
    logger.info("Harmoniq service starting (Manual Single Run via main.py)...")
    try:
        run_all_updates_once()
    except Exception as e:
        logger.exception(f"An unexpected error occurred during the manual run: {e}")
    finally:
        logger.info("Harmoniq manual run finished.")
