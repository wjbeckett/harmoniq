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

        endpoint = f"recommendations/user/{self.api_user}/track"
        params = {'count': limit}

        data = self._make_request(endpoint, params=params)
        recommendations = []

        # Add a check here in case _make_request returns None (e.g., after 404 or other errors)
        if data is None:
             logger.error("Failed to fetch recommendations from ListenBrainz: No data received from API.")
             return [] # Return empty list if the request ultimately failed

        # Proceed with parsing if data is not None
        # Check structure - assuming payload.recommendations might be directly under data now based on other endpoints
        payload = data.get('payload', {}) # Safely get payload, default to empty dict
        raw_recs = payload.get('recommendations', []) # Safely get recommendations, default to empty list


        if raw_recs: # Check if raw_recs is not empty
            # Example structure: { "track_metadata": {"artist_name": "...", "track_name": "..."}, "score": 0.9 }
            for rec in raw_recs:
                track_meta = rec.get('track_metadata') # Recommendations are nested here

                if track_meta:
                    artist_name = track_meta.get('artist_name')
                    track_name = track_meta.get('track_name')

                    if artist_name and track_name:
                        recommendations.append({
                            'artist': artist_name,
                            'title': track_name
                            # Could also store mbid if useful later: 'mbid': track_meta.get('mbid') # Check actual key name
                        })
                    else:
                        logger.warning(f"Skipping malformed ListenBrainz recommendation entry (missing artist/track name in metadata): {rec}")
                else:
                    logger.warning(f"Skipping malformed ListenBrainz recommendation entry (missing track_metadata): {rec}")

            logger.info(f"Successfully processed {len(recommendations)} valid recommendations from ListenBrainz.")
        # Handle cases where payload exists but recommendations list is empty
        elif 'payload' in data and not raw_recs :
             logger.info("ListenBrainz returned recommendations payload, but the list is empty.")
        else: # Handle cases where the structure was unexpected (no payload etc.)
             logger.warning("Could not find 'payload' or 'recommendations' in the expected structure in ListenBrainz response.")
             logger.debug(f"ListenBrainz Response Data: {data}")


        # API already gives a ranked list, limit is handled by API 'count' param
        return recommendations[:limit] # Ensure we don't exceed limit just in case