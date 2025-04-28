# src/harmoniq/lastfm_client.py
import logging
import requests
import time

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
            # This client is optional, so only warn if used without keys
            logger.warning("Last.fm API Key or User not configured. Last.fm features disabled.")
            self.api_key = None
            self.api_user = None
        else:
            self.api_key = api_key
            self.api_user = api_user
            logger.info("Last.fm client initialized.")

    def _make_request(self, params):
        """Makes a request to the Last.fm API with retry logic."""
        if not self.api_key:
            logger.error("Cannot make Last.fm request: API key is not configured.")
            return None

        params['api_key'] = self.api_key
        params['format'] = 'json'
        params['user'] = self.api_user # Most user methods need this

        headers = {'User-Agent': 'Harmoniq Playlist Generator'} # Be a good API citizen

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(LASTFM_API_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = response.json()

                # Check for Last.fm specific errors within the JSON response
                if 'error' in data:
                    error_code = data.get('error')
                    error_message = data.get('message', 'Unknown Last.fm error')
                    logger.error(f"Last.fm API Error {error_code}: {error_message}")
                    # Specific handling? e.g., don't retry on auth errors (code 6?)
                    return None # Or raise a custom exception

                return data

            except requests.exceptions.RequestException as e:
                logger.warning(f"Last.fm request failed (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt + 1 == MAX_RETRIES:
                    logger.error("Max retries reached for Last.fm request.")
                    return None
                time.sleep(RETRY_DELAY * (attempt + 1)) # Exponential backoff might be better
            except Exception as e:
                 logger.error(f"An unexpected error occurred during Last.fm request: {e}")
                 return None # Don't retry on unexpected errors

        return None # Should not be reached if max retries logic is correct

    def get_recommendations(self, limit=config.PLAYLIST_SIZE_LASTFM_RECS):
        """Fetches recommended tracks for the configured user."""
        if not self.api_key or not self.api_user:
            logger.warning("Cannot get recommendations: Last.fm client not configured.")
            return []

        logger.info(f"Fetching {limit} recommendations for user '{self.api_user}' from Last.fm...")
        params = {
            'method': 'user.getrecommendedtracks',
            'limit': limit
            # 'user': self.api_user is added by _make_request
        }
        data = self._make_request(params)
        recommendations = []

        if data and 'recommendations' in data and 'track' in data['recommendations']:
            raw_tracks = data['recommendations']['track']
            if not isinstance(raw_tracks, list): # Handle case where only one track is returned
                raw_tracks = [raw_tracks]

            for track in raw_tracks:
                 # Ensure artist is present and has a name
                 # Sometimes artist is a string directly (less common), sometimes a dict
                artist_name = None
                if 'artist' in track:
                    if isinstance(track['artist'], dict) and 'name' in track['artist']:
                        artist_name = track['artist']['name']
                    elif isinstance(track['artist'], str): # Less common case?
                        artist_name = track['artist']

                if artist_name and 'name' in track:
                    recommendations.append({
                        'artist': artist_name,
                        'title': track['name']
                        # Album info often missing or unreliable in recommendations
                    })
                else:
                    logger.warning(f"Skipping malformed recommendation track: {track}")
            logger.info(f"Successfully fetched {len(recommendations)} valid recommendations from Last.fm.")
        elif data:
             logger.warning("No 'recommendations' or 'track' key found in Last.fm response.")
             logger.debug(f"Last.fm Response Data: {data}")
        else:
            logger.error("Failed to fetch recommendations from Last.fm after retries.")


        return recommendations

    # --- Placeholder for future methods ---
    def get_chart_top_tracks(self, limit=config.PLAYLIST_SIZE_LASTFM_CHARTS):
        """Fetches global top tracks from Last.fm charts."""
        # To be implemented later
        logger.warning("Placeholder: get_chart_top_tracks not implemented.")
        return []