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

        # Construct URL carefully using urljoin to handle slashes
        # Ensure endpoint doesn't start with a slash if base has one
        relative_endpoint = endpoint.lstrip('/')
        url = urllib.parse.urljoin(LISTENBRAINZ_API_URL, relative_endpoint)

        headers = self.auth_header.copy()
        headers['User-Agent'] = 'Harmoniq Playlist Generator v0.3' # Keep version updated?

        # Log the final URL *before* the request
        # Prepare params string for logging (requests does this internally too)
        query_string = urllib.parse.urlencode(params) if params else ""
        full_url_for_log = f"{url}?{query_string}" if query_string else url
        logger.debug(f"Making ListenBrainz request: GET {full_url_for_log}")
        # logger.debug(f"Headers: {headers}") # Can be verbose, enable if needed

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
                # Log status code immediately
                logger.debug(f"Response status code: {response.status_code} from {response.url}")
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                try:
                     data = response.json()
                except requests.exceptions.JSONDecodeError:
                     if response.status_code == 200 and not response.content:
                         logger.warning(f"ListenBrainz request to {endpoint} returned 200 OK with empty body.")
                         return {} # Return empty dict for successful empty response
                     else:
                         logger.error(f"Failed to decode JSON from ListenBrainz response (Status: {response.status_code}, URL: {response.url})")
                         # Log response body if possible (might be large or non-text)
                         try:
                              logger.error(f"Response body: {response.text[:500]}...") # Log first 500 chars
                         except Exception:
                              logger.error("Could not log response body.")
                         # Still raise original error if JSON decode failed on non-empty body
                         raise

                return data

            except requests.exceptions.HTTPError as e:
                 # Handle specific HTTP errors here for better logging/retry logic
                 status_code = e.response.status_code
                 logger.warning(f"ListenBrainz HTTP Error {status_code} (Attempt {attempt + 1}/{MAX_RETRIES}) for {e.request.url}: {e}")
                 if status_code == 401:
                     logger.error("ListenBrainz authentication failed (401). Check token. Aborting request.")
                     return None
                 if status_code == 404:
                     logger.error(f"ListenBrainz endpoint not found (404): {endpoint}. Aborting request for this endpoint.")
                     # Specific handling for the recommendations 404
                     if "recommendations/user" in endpoint:
                          logger.error("This might indicate no recommendations are available for the user or an API issue.")
                     return None # Don't retry 404
                 # Add other status codes to handle if needed (e.g., 400 Bad Request, 429 Rate Limit)
                 if status_code == 400:
                      logger.error(f"ListenBrainz Bad Request (400). Check parameters. Aborting request. Details: {e.response.text}")
                      return None # Don't retry 400

            except requests.exceptions.RequestException as e: # Catch other connection/timeout errors
                logger.warning(f"ListenBrainz connection/timeout error (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                # These are generally retryable

            except Exception as e:
                 logger.exception(f"An unexpected error occurred during ListenBrainz request processing: {e}") # Use exception for trace
                 return None # Don't retry on unexpected errors

            # Retry logic for retryable errors
            if attempt + 1 == MAX_RETRIES:
                logger.error(f"Max retries reached for ListenBrainz request ({endpoint}).")
                return None
            sleep_time = RETRY_DELAY * (attempt + 1)
            logger.info(f"Retrying ListenBrainz request in {sleep_time} seconds...")
            time.sleep(sleep_time)

        return None # Should only be reached if all retries fail


    def get_recommendations(self, limit=config.PLAYLIST_SIZE_LISTENBRAINZ_RECS):
        """
        Fetches recommended tracks. Tries personalized first, falls back to experimental.
        """
        recommendations = []

        # --- Attempt 1: Personalized Endpoint ---
        if self.api_user and self.auth_header:
            logger.info(f"Attempting personalized recommendations fetch for user '{self.api_user}' from ListenBrainz...")
            # Correct documented endpoint path
            endpoint_pers = f"recommendations/user/{self.api_user}/track"
            params_pers = {'count': limit}
            data_pers = self._make_request(endpoint_pers, params=params_pers)

            # --- Handling based on _make_request result ---
            if data_pers is not None: # Request did not fail with None (e.g., it wasn't a 404/401 or max retries)
                payload_pers = data_pers.get('payload', {})
                raw_recs_pers = payload_pers.get('recommendations', [])
                if raw_recs_pers:
                    logger.info("Successfully fetched data from PERSONALIZED recommendations endpoint.")
                    # (Parsing logic remains the same)
                    for rec in raw_recs_pers:
                        track_meta = rec.get('track_metadata')
                        if track_meta:
                            artist_name = track_meta.get('artist_name')
                            track_name = track_meta.get('track_name')
                            if artist_name and track_name:
                                recommendations.append({'artist': artist_name, 'title': track_name})
                            else: logger.warning(f"Skipping malformed LB rec (pers): {rec}")
                        else: logger.warning(f"Skipping malformed LB rec (pers): {rec}")
                    logger.info(f"Processed {len(recommendations)} tracks from personalized recommendations.")
                    # If we got personalized recs, RETURN them immediately
                    return recommendations[:limit]
                else:
                    # Endpoint returned OK, but the list was empty
                    logger.info("Personalized recommendations endpoint returned successfully but the list was empty. Will try experimental.")
            # else: Failure (e.g., 404) was already logged within _make_request

        # --- Attempt 2: Experimental Endpoint (Fallback if personalized failed or returned empty) ---
        logger.info("Falling back to fetching EXPERIMENTAL track recommendations from ListenBrainz...")
        endpoint_exp = "recommendations/track/experimental"
        params_exp = {'count': limit}
        data_exp = self._make_request(endpoint_exp, params=params_exp)

        if data_exp is None:
             logger.error("Failed to fetch recommendations from ListenBrainz experimental endpoint as well.")
             return [] # Both attempts failed

        payload_exp = data_exp.get('payload', {})
        raw_recs_exp = payload_exp.get('recommendations', [])

        if raw_recs_exp:
            logger.info("Successfully fetched data from EXPERIMENTAL recommendations endpoint.")
            # (Parsing logic remains the same)
            for rec in raw_recs_exp:
                track_meta = rec.get('track_metadata')
                if track_meta:
                    artist_name = track_meta.get('artist_name')
                    track_name = track_meta.get('track_name')
                    if artist_name and track_name:
                        recommendations.append({'artist': artist_name, 'title': track_name})
                    else: logger.warning(f"Skipping malformed LB rec (exp): {rec}")
                else: logger.warning(f"Skipping malformed LB rec (exp): {rec}")
            logger.info(f"Processed {len(recommendations)} tracks from experimental recommendations.")
        elif 'payload' in data_exp and not raw_recs_exp :
             logger.info("ListenBrainz experimental endpoint returned recommendations payload, but the list is empty.")
        else:
             logger.warning("Could not find 'payload' or 'recommendations' in the expected structure in ListenBrainz experimental response.")
             logger.debug(f"ListenBrainz Experimental Response Data: {data_exp}")

        return recommendations[:limit]