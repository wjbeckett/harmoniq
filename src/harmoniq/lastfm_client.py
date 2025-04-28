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

    def _make_request(self, params, use_user=True): # Added use_user flag
        """Makes a request to the Last.fm API with retry logic."""
        if not self.api_key:
            logger.error("Cannot make Last.fm request: API key is not configured.")
            return None

        # Ensure default parameters are set
        params.setdefault('api_key', self.api_key)
        params.setdefault('format', 'json')
        if use_user and self.api_user: # Only add user if needed and available
             params.setdefault('user', self.api_user)

        headers = {'User-Agent': 'Harmoniq Playlist Generator v0.1'} # Be a good API citizen

        request_url = params.pop('request_url', LASTFM_API_URL) # Allow overriding base URL if needed later

        logger.debug(f"Making Last.fm request: method={params.get('method')}, params={ {k:v for k,v in params.items() if k not in ['api_key']} }") # Log params except key

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(request_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = response.json()

                # Check for Last.fm specific errors within the JSON response
                if isinstance(data, dict) and 'error' in data:
                    error_code = data.get('error')
                    error_message = data.get('message', 'Unknown Last.fm error')
                    logger.error(f"Last.fm API Error {error_code}: {error_message} for method {params.get('method')}")
                    # Specific handling? e.g., don't retry on auth errors (code 6?) or param errors (code 3?)
                    if error_code == 3: # Invalid method or parameters, no point retrying
                         return None
                    # Consider other non-retry errors?
                    # If retrying, continue loop implicitly

                else:
                    # Success!
                    return data # Return the parsed JSON data

            except requests.exceptions.RequestException as e:
                logger.warning(f"Last.fm request failed (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                # Continue to retry after delay

            except Exception as e:
                 logger.error(f"An unexpected error occurred during Last.fm request processing: {e}")
                 # Don't retry on unexpected parsing/logic errors, break and return None
                 return None

            # If we are here, it means a retryable error occurred
            if attempt + 1 == MAX_RETRIES:
                logger.error(f"Max retries reached for Last.fm request (method: {params.get('method')}).")
                return None
            sleep_time = RETRY_DELAY * (attempt + 1) # Basic linear backoff
            logger.info(f"Retrying Last.fm request in {sleep_time} seconds...")
            time.sleep(sleep_time)

        return None # Should only be reached if loop completes without success

    def get_recommendations(self, limit=config.PLAYLIST_SIZE_LASTFM_RECS, artists_to_consider=20, tracks_per_artist=3):
        """
        Fetches recommended tracks derived from recommended artists' top tracks.
        """
        if not self.api_key or not self.api_user:
            logger.warning("Cannot get recommendations: Last.fm client not configured.")
            return []

        logger.info(f"Fetching derived recommendations for user '{self.api_user}' from Last.fm...")
        logger.info(f"(Fetching top {artists_to_consider} recommended artists, then top {tracks_per_artist} tracks each)")

        # 1. Get Recommended Artists
        rec_artists_params = {
            'method': 'user.getRecommendedArtists',
            'limit': artists_to_consider
        }
        artists_data = self._make_request(rec_artists_params)
        recommended_artists = []

        if artists_data and 'recommendations' in artists_data and 'artist' in artists_data['recommendations']:
            raw_artists = artists_data['recommendations']['artist']
            if not isinstance(raw_artists, list):
                raw_artists = [raw_artists]
            for artist in raw_artists:
                if 'name' in artist:
                    recommended_artists.append(artist['name'])
            logger.info(f"Found {len(recommended_artists)} recommended artists.")
        else:
            logger.error("Could not fetch recommended artists from Last.fm.")
            return []

        # 2. Get Top Tracks for each Recommended Artist
        all_top_tracks = []
        processed_artists = 0
        for artist_name in recommended_artists:
            # Add a small delay to avoid hitting rate limits too quickly
            time.sleep(0.2) # 200ms delay between artist lookups
            logger.debug(f"Fetching top tracks for recommended artist: {artist_name}")
            top_tracks_params = {
                'method': 'artist.getTopTracks',
                'artist': artist_name,
                'limit': tracks_per_artist,
                 # Note: artist.getTopTracks does NOT use the 'user' param
                 'autocorrect': 1 # Help with slight name variations
            }
            tracks_data = self._make_request(top_tracks_params, use_user=False) # Don't send user param

            if tracks_data and 'toptracks' in tracks_data and 'track' in tracks_data['toptracks']:
                raw_tracks = tracks_data['toptracks']['track']
                if not isinstance(raw_tracks, list):
                    raw_tracks = [raw_tracks]
                for track in raw_tracks:
                    # Ensure basic structure
                    if 'name' in track and 'artist' in track and 'name' in track['artist']:
                         all_top_tracks.append({
                             'artist': track['artist']['name'], # Use artist name from this result
                             'title': track['name']
                         })
                    else:
                         logger.warning(f"Skipping malformed top track entry for artist {artist_name}: {track}")
            else:
                 logger.warning(f"Could not fetch top tracks for artist: {artist_name}")

            processed_artists += 1
            if len(all_top_tracks) >= limit * 1.5: # Fetch slightly more than needed to allow for shuffle/sampling
                 logger.info(f"Collected enough potential tracks after processing {processed_artists} artists.")
                 break # Stop fetching if we likely have enough tracks

        if not all_top_tracks:
            logger.error("No top tracks found for any recommended artists.")
            return []

        # 3. Deduplicate and Limit
        # Simple deduplication based on (artist, title) tuple
        seen_tracks = set()
        unique_tracks = []
        for track in all_top_tracks:
            track_tuple = (track['artist'].lower(), track['title'].lower())
            if track_tuple not in seen_tracks:
                unique_tracks.append(track)
                seen_tracks.add(track_tuple)

        logger.info(f"Collected {len(all_top_tracks)} tracks total, {len(unique_tracks)} unique.")

        # 4. Shuffle and select the final list
        random.shuffle(unique_tracks)
        final_recommendations = unique_tracks[:limit]

        logger.info(f"Returning final list of {len(final_recommendations)} derived recommendations.")
        return final_recommendations


    def get_chart_top_tracks(self, limit=config.PLAYLIST_SIZE_LASTFM_CHARTS):
        """Fetches global top tracks from Last.fm charts."""
        if not self.api_key:
            logger.warning("Cannot get chart tracks: Last.fm client not configured.")
            return []

        logger.info(f"Fetching top {limit} chart tracks from Last.fm...")
        params = {
            'method': 'chart.getTopTracks',
            'limit': limit
        }
        data = self._make_request(params, use_user=False) # Chart doesn't need user
        chart_tracks = []

        if data and 'tracks' in data and 'track' in data['tracks']:
             raw_tracks = data['tracks']['track']
             if not isinstance(raw_tracks, list):
                 raw_tracks = [raw_tracks]
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