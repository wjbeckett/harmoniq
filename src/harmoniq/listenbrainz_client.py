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

        # Construct URL manually, ensuring no double slashes
        url = LISTENBRAINZ_API_URL.rstrip('/') + '/' + endpoint.lstrip('/')

        headers = self.auth_header.copy()
        headers['User-Agent'] = 'Harmoniq Playlist Generator v0.4'

        # Log the final URL *before* the request
        # Prepare params string for logging (requests does this internally too)
        # query_string = urllib.parse.urlencode(params) if params else "" # Need import if using this
        query_string = "&".join([f"{k}={v}" for k,v in params.items()]) if params else ""
        full_url_for_log = f"{url}?{query_string}" if query_string else url
        masked_headers = {k: (v[:10] + "..." if k == "Authorization" else v) for k, v in headers.items()}
        logger.debug(f"Making ListenBrainz request: GET {full_url_for_log}")
        logger.debug(f"Headers: {masked_headers}")


        for attempt in range(MAX_RETRIES):
            try:
                # First try WITHOUT params to check base endpoint existence if it's a 404 check
                if attempt == 0: # Only try param-less on first attempt
                     logger.debug(f"Checking base endpoint existence first (no params): GET {url}")
                     base_response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                     logger.debug(f"Base endpoint check status code: {base_response.status_code}")
                     # Don't raise_for_status here, just check if it's 404
                     if base_response.status_code == 404:
                         logger.error(f"Base endpoint {url} returned 404. Endpoint likely does not exist.")
                         # Abort retries for this endpoint if the base path is 404
                         return None
                     # If base endpoint exists (e.g. 200 OK even if needs params, or 400/401), proceed with params

                # Proceed with the actual request including parameters
                response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
                logger.debug(f"Full request response status code: {response.status_code} from {response.url}") # Log URL returned by request
                response.raise_for_status()

                try:
                     data = response.json()
                except requests.exceptions.JSONDecodeError:
                     if response.status_code == 200 and not response.content:
                         logger.warning(f"ListenBrainz request to {endpoint} returned 200 OK with empty body.")
                         return {}
                     else:
                         logger.error(f"Failed to decode JSON from ListenBrainz response (Status: {response.status_code}, URL: {response.url})")
                         try: logger.error(f"Response body: {response.text[:500]}...")
                         except Exception: logger.error("Could not log response body.")
                         raise
                return data

            except requests.exceptions.HTTPError as e:
                 status_code = e.response.status_code
                 logger.warning(f"ListenBrainz HTTP Error {status_code} (Attempt {attempt + 1}/{MAX_RETRIES}) for {e.request.url}: {e}")
                 if status_code in [401, 404, 400]: # Non-retryable errors
                     logger.error(f"Non-retryable HTTP error {status_code}. Aborting request for {endpoint}.")
                     # Specific message for persistent 404 on recommendations
                     if status_code == 404 and "recommendations" in endpoint:
                         logger.error("The recommendations endpoint returned 404. It may be unavailable or require different access.")
                     return None
                 # Allow retries for other HTTP errors (e.g., 5xx Server Errors)

            except requests.exceptions.RequestException as e:
                logger.warning(f"ListenBrainz connection/timeout error (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")

            except Exception as e:
                 logger.exception(f"An unexpected error occurred during ListenBrainz request processing: {e}")
                 return None

            # Retry logic
            if attempt + 1 == MAX_RETRIES:
                logger.error(f"Max retries reached for ListenBrainz request ({endpoint}).")
                return None
            sleep_time = RETRY_DELAY * (attempt + 1)
            logger.info(f"Retrying ListenBrainz request in {sleep_time} seconds...")
            time.sleep(sleep_time)

        return None


    def get_recommendations(self, limit=config.PLAYLIST_SIZE_LISTENBRAINZ_RECS):
        """
        Fetches recommended tracks. Tries personalized first, falls back to experimental.
        """
        recommendations = []

        # --- Attempt 1: Personalized Endpoint ---
        if self.api_user and self.auth_header:
            logger.info(f"Attempting personalized recommendations fetch for user '{self.api_user}' from ListenBrainz...")
            endpoint_pers = f"recommendations/user/{self.api_user}/track"
            params_pers = {'count': limit}
            data_pers = self._make_request(endpoint_pers, params=params_pers)

            if data_pers is not None:
                payload_pers = data_pers.get('payload', {})
                raw_recs_pers = payload_pers.get('recommendations', [])
                if raw_recs_pers:
                    logger.info("Successfully fetched data from PERSONALIZED recommendations endpoint.")
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
                    return recommendations[:limit]
                else:
                    logger.info("Personalized recommendations endpoint returned successfully but list was empty. Will try experimental.")
            # else: Failure (404/401/etc.) already logged by _make_request

        # --- Attempt 2: Experimental Endpoint ---
        logger.info("Falling back to fetching EXPERIMENTAL track recommendations from ListenBrainz...")
        endpoint_exp = "recommendations/track/experimental"
        params_exp = {'count': limit}
        data_exp = self._make_request(endpoint_exp, params=params_exp)

        if data_exp is None:
             logger.error("Failed to fetch recommendations from ListenBrainz experimental endpoint as well.")
             return []

        payload_exp = data_exp.get('payload', {})
        raw_recs_exp = payload_exp.get('recommendations', [])

        if raw_recs_exp:
            logger.info("Successfully fetched data from EXPERIMENTAL recommendations endpoint.")
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