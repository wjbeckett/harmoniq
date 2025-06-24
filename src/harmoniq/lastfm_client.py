# src/harmoniq/lastfm_client.py
import logging
import requests
import time
import random

# Import config variables
from . import config

logger = logging.getLogger(__name__)

LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
REQUEST_TIMEOUT = 15  # Seconds
RETRY_DELAY = 5  # Seconds
MAX_RETRIES = 3


class LastfmClient:
    """Handles interactions with the Last.fm API."""

    def __init__(self, api_key=config.LASTFM_API_KEY, api_user=config.LASTFM_USER):
        if not api_key or not api_user:
            logger.warning(
                "Last.fm API Key or User not configured. Last.fm features disabled."
            )
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
        params.setdefault("api_key", self.api_key)
        params.setdefault("format", "json")
        if use_user and self.api_user:  # Only add user if needed and available
            params.setdefault("user", self.api_user)

        headers = {"User-Agent": "Harmoniq Playlist Generator v0.2"}  # Updated version

        request_url = params.pop("request_url", LASTFM_API_URL)

        # Clean up params for logging (remove api_key)
        log_params = {k: v for k, v in params.items() if k != "api_key"}
        logger.debug(
            f"Making Last.fm request: method={params.get('method')}, params={log_params}"
        )

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    request_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict) and "error" in data:
                    error_code = data.get("error")
                    error_message = data.get("message", "Unknown Last.fm error")
                    logger.error(
                        f"Last.fm API Error {error_code}: {error_message} for method {params.get('method')}"
                    )
                    # Added specific error checks based on common codes
                    if error_code in [
                        3,
                        6,
                        8,
                        9,
                        10,
                        11,
                        13,
                        16,
                        26,
                        29,
                    ]:  # Invalid method, params, auth, key, limits, etc.
                        logger.error(
                            f"Non-retryable Last.fm error ({error_code}). Aborting request."
                        )
                        return None  # No point retrying these
                    # Otherwise, assume temporary issue and allow retry loop to continue

                else:
                    # Success!
                    return data

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Last.fm request failed (Attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                # Continue to retry after delay

            except Exception as e:
                logger.error(
                    f"An unexpected error occurred during Last.fm request processing: {e}"
                )
                return None

            # If we are here, it means a retryable error occurred
            if attempt + 1 == MAX_RETRIES:
                logger.error(
                    f"Max retries reached for Last.fm request (method: {params.get('method')})."
                )
                return None
            sleep_time = RETRY_DELAY * (attempt + 1)
            logger.info(f"Retrying Last.fm request in {sleep_time} seconds...")
            time.sleep(sleep_time)

        return None
