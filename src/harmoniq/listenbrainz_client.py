# src/harmoniq/listenbrainz_client.py
import logging
import requests
import time

# Import config variables
from . import config

logger = logging.getLogger(__name__)

LISTENBRAINZ_API_URL = "https://api.listenbrainz.org/1/"
REQUEST_TIMEOUT = 20 # ListenBrainz might sometimes be slower
RETRY_DELAY = 7
MAX_RETRIES = 3

class ListenBrainzClient:
    """Handles interactions with the ListenBrainz API."""

    def __init__(self, user_token=config.LISTENBRAINZ_USER_TOKEN):
        if not user_token:
            logger.warning("ListenBrainz User Token not configured. ListenBrainz features disabled.")
            self.user_token = None
            self.auth_header = None
            self.api_user = None # Need to fetch username separately if needed
        else:
            self.user_token = user_token
            self.auth_header = {'Authorization': f'Token {self.user_token}'}
            # We might need the username for the URL, let's try validating the token first
            # and potentially getting the username
            self._validate_token_and_get_user()
            if self.api_user:
                 logger.info(f"ListenBrainz client initialized for user: {self.api_user}")
            else:
                 logger.error("ListenBrainz client initialization failed: Could not validate token or get username.")
                 # Effectively disable the client if validation fails
                 self.user_token = None
                 self.auth_header = None


    def _validate_token_and_get_user(self):
        """Validate the token and get the associated username."""
        if not self.auth_header: return
        try:
            logger.info("Validating ListenBrainz token...")
            response = requests.get(
                LISTENBRAINZ_API_URL + "validate-token",
                headers=self.auth_header,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            if data.get('valid'):
                self.api_user = data.get('user_name')
                logger.info(f"ListenBrainz token validated successfully for user '{self.api_user}'.")
            else:
                logger.error(f"ListenBrainz token validation failed: {data.get('message', 'Unknown error')}")
                self.api_user = None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error validating ListenBrainz token: {e}")
            self.api_user = None

    def _make_request(self, endpoint, params=None):
        """Makes a request to the ListenBrainz API with retry logic."""
        if not self.auth_header:
            logger.error("Cannot make ListenBrainz request: Client not initialized or token invalid.")
            return None

        url = LISTENBRAINZ_API_URL + endpoint
        headers = self.auth_header.copy()
        headers['User-Agent'] = 'Harmoniq Playlist Generator v0.3'

        logger.debug(f"Making ListenBrainz request: endpoint={endpoint}, params={params}")

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                # ListenBrainz API might return empty body on success for some endpoints?
                # Handle potential JSON decode error for empty responses
                try:
                     data = response.json()
                except requests.exceptions.JSONDecodeError:
                     if response.status_code == 200 and not response.content:
                         logger.warning(f"ListenBrainz request to {endpoint} returned 200 OK with empty body.")
                         return {} # Return empty dict for successful empty response
                     else:
                         logger.error(f"Failed to decode JSON from ListenBrainz response (Status: {response.status_code})")
                         raise # Re-raise the JSONDecodeError if content is not empty

                # Assuming ListenBrainz doesn't embed errors like Last.fm, rely on HTTP status codes
                return data

            except requests.exceptions.RequestException as e:
                logger.warning(f"ListenBrainz request failed (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                # Check if it's an auth error (401) - no point retrying
                if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 401:
                     logger.error("ListenBrainz authentication failed (401). Check token. Aborting request.")
                     return None
                # Check for other non-retryable errors? (e.g., 404 Not Found?)
                if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 404:
                     logger.error(f"ListenBrainz endpoint not found (404): {endpoint}. Aborting request.")
                     return None

                if attempt + 1 == MAX_RETRIES:
                    logger.error(f"Max retries reached for ListenBrainz request ({endpoint}).")
                    return None
                sleep_time = RETRY_DELAY * (attempt + 1)
                logger.info(f"Retrying ListenBrainz request in {sleep_time} seconds...")
                time.sleep(sleep_time)
            except Exception as e:
                 logger.error(f"An unexpected error occurred during ListenBrainz request processing: {e}")
                 return None # Don't retry on unexpected errors

        return None

    def get_recommendations(self, limit=config.PLAYLIST_SIZE_LISTENBRAINZ_RECS):
        """Fetches recommended tracks for the validated user."""
        if not self.api_user or not self.auth_header:
            logger.warning("Cannot get recommendations: ListenBrainz client not configured or user not validated.")
            return []

        logger.info(f"Fetching {limit} recommendations for user '{self.api_user}' from ListenBrainz...")
        # Note: The API uses 'count' not 'limit'
        endpoint = f"user/{self.api_user}/recommendations/track"
        params = {'count': limit}

        data = self._make_request(endpoint, params=params)
        recommendations = []

        if data and 'payload' in data and 'recommendations' in data['payload']:
            raw_recs = data['payload']['recommendations']
            # Structure is slightly different, contains track MBIDs etc.
            # Example: { "track_mbid": "...", "track_name": "...", "artist_mbid": "...", "artist_name": "...", "score": 0.9 }
            for rec in raw_recs:
                track_meta = rec.get('track_metadata', {}) # Recommendations might be inside track_metadata now? Check API docs again if needed.
                # Let's assume simpler structure first based on example:
                artist_name = rec.get('artist_name')
                track_name = rec.get('track_name')

                if artist_name and track_name:
                    recommendations.append({
                        'artist': artist_name,
                        'title': track_name
                        # Could also store mbid if useful later: 'mbid': rec.get('track_mbid')
                    })
                else:
                    # Fallback check inside track_metadata if the simpler structure failed
                    artist_name_meta = track_meta.get('artist_name')
                    track_name_meta = track_meta.get('track_name')
                    if artist_name_meta and track_name_meta:
                         recommendations.append({
                            'artist': artist_name_meta,
                            'title': track_name_meta
                        })
                    else:
                         logger.warning(f"Skipping malformed ListenBrainz recommendation entry: {rec}")

            logger.info(f"Successfully fetched {len(recommendations)} valid recommendations from ListenBrainz.")
        elif data:
             logger.warning("No 'payload' or 'recommendations' key found in ListenBrainz response.")
             logger.debug(f"ListenBrainz Response Data: {data}")
        else:
             logger.error("Failed to fetch recommendations from ListenBrainz after retries.")

        # API already gives a ranked list, limit is handled by API 'count' param
        return recommendations[:limit] # Ensure we don't exceed limit if API returns slightly more?