# src/harmoniq/lastfm_client.py
import logging
import requests
import time
import random

# Import config variables
from . import config

logger = logging.getLogger(__name__)

LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
REQUEST_TIMEOUT = 15 # Seconds
RETRY_DELAY = 5 # Seconds
MAX_RETRIES = 3

class LastfmClient:
    """Handles interactions with the Last.fm API."""

    def __init__(self, api_key=config.LASTFM_API_KEY, api_user=config.LASTFM_USER):
        if not api_key or not api_user:
            logger.warning("Last.fm API Key or User not configured. Last.fm features disabled.")
            self.api_key = None
            self.api_user = None
        else:
            self.api_key = api_key
            self.api_user = api_user
            logger.info("Last.fm client initialized.")

    def _make_request(self, params, use_user=True):
        """Makes a request to the Last.fm API with retry logic."""
        if not self.api_key:
            logger.error("Cannot make Last.fm request: API key is not configured.")
            return None

        # Ensure default parameters are set
        params.setdefault('api_key', self.api_key)
        params.setdefault('format', 'json')
        if use_user and self.api_user: # Only add user if needed and available
             params.setdefault('user', self.api_user)

        headers = {'User-Agent': 'Harmoniq Playlist Generator v0.2'} # Updated version

        request_url = params.pop('request_url', LASTFM_API_URL)

        # Clean up params for logging (remove api_key)
        log_params = {k:v for k,v in params.items() if k != 'api_key'}
        logger.debug(f"Making Last.fm request: method={params.get('method')}, params={log_params}")

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(request_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict) and 'error' in data:
                    error_code = data.get('error')
                    error_message = data.get('message', 'Unknown Last.fm error')
                    logger.error(f"Last.fm API Error {error_code}: {error_message} for method {params.get('method')}")
                    # Added specific error checks based on common codes
                    if error_code in [3, 6, 8, 9, 10, 11, 13, 16, 26, 29]: # Invalid method, params, auth, key, limits, etc.
                        logger.error(f"Non-retryable Last.fm error ({error_code}). Aborting request.")
                        return None # No point retrying these
                    # Otherwise, assume temporary issue and allow retry loop to continue

                else:
                    # Success!
                    return data

            except requests.exceptions.RequestException as e:
                logger.warning(f"Last.fm request failed (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                # Continue to retry after delay

            except Exception as e:
                 logger.error(f"An unexpected error occurred during Last.fm request processing: {e}")
                 return None

            # If we are here, it means a retryable error occurred
            if attempt + 1 == MAX_RETRIES:
                logger.error(f"Max retries reached for Last.fm request (method: {params.get('method')}).")
                return None
            sleep_time = RETRY_DELAY * (attempt + 1)
            logger.info(f"Retrying Last.fm request in {sleep_time} seconds...")
            time.sleep(sleep_time)

        return None

    def get_recommendations(self,
                            limit=config.PLAYLIST_SIZE_LASTFM_RECS,
                            top_artists_to_use=15, # How many of the user's top artists to base recs on
                            similar_artists_per_top=5, # How many similar artists to find for each top artist
                            tracks_per_similar_artist=2): # How many top tracks to get for each similar artist
        """
        Fetches recommended tracks derived from artists similar to the user's top artists.
        Uses documented API methods: user.getTopArtists -> artist.getSimilar -> artist.getTopTracks
        """
        if not self.api_key or not self.api_user:
            logger.warning("Cannot get recommendations: Last.fm client not configured.")
            return []

        logger.info(f"Fetching derived recommendations for user '{self.api_user}' from Last.fm...")
        logger.info(f"(Using top {top_artists_to_use} artists -> {similar_artists_per_top} similar each -> {tracks_per_similar_artist} tracks each)")

        # 1. Get User's Top Artists
        top_artists_params = {
            'method': 'user.getTopArtists',
            'limit': top_artists_to_use,
            'period': '6month' # Consider making period configurable? ('overall', '12month', '6month', '3month', '1month', '7day')
        }
        top_artists_data = self._make_request(top_artists_params)
        user_top_artists = []
        if top_artists_data and 'topartists' in top_artists_data and 'artist' in top_artists_data['topartists']:
            raw_artists = top_artists_data['topartists']['artist']
            if not isinstance(raw_artists, list): raw_artists = [raw_artists]
            for artist in raw_artists:
                if 'name' in artist:
                    user_top_artists.append(artist['name'])
            logger.info(f"Found {len(user_top_artists)} top artists for user.")
        else:
            logger.error("Could not fetch top artists for user from Last.fm.")
            return []

        # 2. Get Similar Artists for each Top Artist
        similar_artists_pool = set() # Use a set to automatically handle duplicates
        processed_top_artists = 0
        for top_artist_name in user_top_artists:
            time.sleep(0.2) # API Delay
            logger.debug(f"Fetching similar artists for top artist: {top_artist_name}")
            similar_params = {
                'method': 'artist.getSimilar',
                'artist': top_artist_name,
                'limit': similar_artists_per_top,
                'autocorrect': 1
            }
            similar_data = self._make_request(similar_params, use_user=False)
            if similar_data and 'similarartists' in similar_data and 'artist' in similar_data['similarartists']:
                raw_similar = similar_data['similarartists']['artist']
                if not isinstance(raw_similar, list): raw_similar = [raw_similar]
                count = 0
                for artist in raw_similar:
                    if 'name' in artist:
                        similar_artists_pool.add(artist['name'])
                        count += 1
                logger.debug(f"Added {count} similar artists from {top_artist_name}")
            else:
                logger.warning(f"Could not fetch similar artists for: {top_artist_name}")
            processed_top_artists += 1
            # Optional: Stop early if pool is large enough?
            # if len(similar_artists_pool) > limit * 2: break

        # Remove the user's original top artists from the similar pool to ensure novelty
        original_top_set = set(a.lower() for a in user_top_artists)
        final_similar_artists = [a for a in similar_artists_pool if a.lower() not in original_top_set]

        if not final_similar_artists:
            logger.error("No similar artists found after processing user's top artists.")
            return []
        logger.info(f"Found {len(similar_artists_pool)} potential similar artists, {len(final_similar_artists)} unique and novel artists to explore.")


        # 3. Get Top Tracks for each Similar Artist
        all_potential_tracks = []
        processed_similar_artists = 0
        # Shuffle the similar artists list to get variety if we hit limits early
        random.shuffle(final_similar_artists)

        for similar_artist_name in final_similar_artists:
            time.sleep(0.2) # API Delay
            logger.debug(f"Fetching top tracks for similar artist: {similar_artist_name}")
            top_tracks_params = {
                'method': 'artist.getTopTracks',
                'artist': similar_artist_name,
                'limit': tracks_per_similar_artist,
                'autocorrect': 1
            }
            tracks_data = self._make_request(top_tracks_params, use_user=False)

            if tracks_data and 'toptracks' in tracks_data and 'track' in tracks_data['toptracks']:
                raw_tracks = tracks_data['toptracks']['track']
                if not isinstance(raw_tracks, list): raw_tracks = [raw_tracks]
                for track in raw_tracks:
                    if 'name' in track and 'artist' in track and 'name' in track['artist']:
                         all_potential_tracks.append({
                             'artist': track['artist']['name'],
                             'title': track['name']
                         })
                    else:
                         logger.warning(f"Skipping malformed top track entry for artist {similar_artist_name}: {track}")
            else:
                 logger.warning(f"Could not fetch top tracks for similar artist: {similar_artist_name}")

            processed_similar_artists += 1
            # Stop fetching if we have significantly more tracks than needed (allows for dedupe/sampling)
            if len(all_potential_tracks) >= limit * 2.0:
                 logger.info(f"Collected enough potential tracks ({len(all_potential_tracks)}) after processing {processed_similar_artists} similar artists.")
                 break

        if not all_potential_tracks:
            logger.error("No top tracks found for any similar artists.")
            return []

        # 4. Deduplicate and Select Final Tracks
        seen_tracks = set()
        unique_tracks = []
        for track in all_potential_tracks:
            # Simple dedupe by lowercase artist/title
            track_tuple = (track['artist'].lower().strip(), track['title'].lower().strip())
            if track_tuple not in seen_tracks:
                unique_tracks.append(track)
                seen_tracks.add(track_tuple)

        logger.info(f"Collected {len(all_potential_tracks)} tracks total, {len(unique_tracks)} unique.")

        # Shuffle and limit
        random.shuffle(unique_tracks)
        final_recommendations = unique_tracks[:limit]

        logger.info(f"Returning final list of {len(final_recommendations)} derived recommendations.")
        return final_recommendations


    def get_chart_top_tracks(self, limit=config.PLAYLIST_SIZE_LASTFM_CHARTS):
        """Fetches global top tracks from Last.fm charts."""
        # This method should still be valid based on docs
        if not self.api_key:
            logger.warning("Cannot get chart tracks: Last.fm client not configured.")
            return []

        logger.info(f"Fetching top {limit} chart tracks from Last.fm...")
        params = {
            'method': 'chart.getTopTracks',
            'limit': limit
        }
        data = self._make_request(params, use_user=False)
        chart_tracks = []

        if data and 'tracks' in data and 'track' in data['tracks']:
             raw_tracks = data['tracks']['track']
             if not isinstance(raw_tracks, list): raw_tracks = [raw_tracks]
             for track in raw_tracks:
                 if 'name' in track and 'artist' in track and 'name' in track['artist']:
                      chart_tracks.append({
                          'artist': track['artist']['name'],
                          'title': track['name']
                      })
                 else:
                      logger.warning(f"Skipping malformed chart track entry: {track}")
             logger.info(f"Successfully fetched {len(chart_tracks)} valid chart tracks from Last.fm.")
        elif data:
             logger.warning("No 'tracks' or 'track' key found in Last.fm chart response.")
             logger.debug(f"Last.fm Response Data: {data}")
        else:
             logger.error("Failed to fetch chart tracks from Last.fm after retries.")

        return chart_tracks