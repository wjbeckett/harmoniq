# src/harmoniq/lastfm_client.py
import logging
import requests
import time

# random is not needed anymore if we remove the track recommendation shuffling

# Import config variables
from . import config  # Used for api_key, api_user defaults in __init__

logger = logging.getLogger(__name__)

LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
REQUEST_TIMEOUT = 15  # Seconds
RETRY_DELAY = 5  # Seconds
MAX_RETRIES = 3


class LastfmClient:
    """Handles interactions with the Last.fm API for Library Grower."""

    def __init__(self, api_key=config.LASTFM_API_KEY, api_user=config.LASTFM_USER):
        if not api_key or not api_user:  # Last.fm is essential for Library Grower
            logger.error(
                "Last.fm API Key or User not configured. Library Grower cannot function."
            )
            self.api_key = None
            self.api_user = None
            # raise ValueError("Last.fm API Key and User are required for Library Grower.") # Or handle this in main logic
        else:
            self.api_key = api_key
            self.api_user = api_user
            logger.info("Last.fm client initialized for Library Grower.")

    def _make_request(
        self, params, use_user_param_in_request=True
    ):  # Renamed param for clarity
        """Makes a request to the Last.fm API with retry logic."""
        if not self.api_key:
            logger.error("Cannot make Last.fm request: API key is not configured.")
            return None

        params["api_key"] = self.api_key
        params["format"] = "json"

        # Some methods don't use 'user' (e.g. artist.getSimilar, artist.getTopAlbums, album.getInfo)
        # Some methods require 'user' (e.g. user.getTopArtists)
        if use_user_param_in_request and self.api_user:
            params["user"] = self.api_user

        headers = {"User-Agent": "Harmoniq Library Grower v0.1"}
        request_url = params.pop("request_url", LASTFM_API_URL)
        log_params = {k: v for k, v in params.items() if k != "api_key"}  # For logging
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
                    err_code = data.get("error")
                    err_msg = data.get("message", "Unknown Last.fm error")
                    logger.error(
                        f"Last.fm API Error {err_code}: {err_msg} for method {params.get('method')}"
                    )
                    if err_code in [3, 6, 8, 9, 10, 11, 13, 16, 26, 29]:
                        return None  # Non-retryable
                else:
                    return data
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Last.fm request failed (Attempt {attempt+1}/{MAX_RETRIES}): {e}"
                )
            except Exception as e:
                logger.error(f"Unexpected error during Last.fm request processing: {e}")
                return None
            if attempt + 1 == MAX_RETRIES:
                logger.error(f"Max retries for Last.fm method: {params.get('method')}.")
                return None
            time.sleep(RETRY_DELAY * (attempt + 1))
        return None

    def get_user_top_artists(
        self, period: str = "6month", limit: int = 30
    ) -> list[dict]:
        """Fetches the user's top artists."""
        if not self.api_key or not self.api_user:
            logger.warning("Last.fm not configured for get_user_top_artists.")
            return []

        logger.info(
            f"Fetching top {limit} artists for user '{self.api_user}' (period: {period})..."
        )
        params = {"method": "user.getTopArtists", "limit": limit, "period": period}
        data = self._make_request(params, use_user_param_in_request=True)

        artists = []
        if data and "topartists" in data and "artist" in data["topartists"]:
            raw_artists = data["topartists"]["artist"]
            if not isinstance(raw_artists, list):
                raw_artists = [raw_artists]  # Handle single result
            for artist_data in raw_artists:
                if (
                    "name" in artist_data and "mbid" in artist_data
                ):  # Require name and mbid
                    artists.append(
                        {
                            "name": artist_data["name"],
                            "mbid": artist_data["mbid"],
                            "playcount": artist_data.get("playcount"),
                        }
                    )
                else:
                    logger.warning(
                        f"Skipping top artist with missing name or MBID: {artist_data}"
                    )
            logger.info(f"Found {len(artists)} top artists for user.")
        else:
            logger.error(
                f"Could not fetch top artists for user '{self.api_user}'. Response: {data}"
            )
        return artists

    def get_similar_artists(
        self, artist_name: str = None, artist_mbid: str = None, limit: int = 5
    ) -> list[dict]:
        """Fetches artists similar to a given artist, by name or MBID."""
        if not self.api_key:
            logger.warning("Last.fm not configured for get_similar_artists.")
            return []
        if not artist_name and not artist_mbid:
            logger.error("Artist name or MBID required for get_similar_artists.")
            return []

        log_identifier = artist_mbid if artist_mbid else artist_name
        logger.info(f"Fetching {limit} artists similar to '{log_identifier}'...")
        params = {"method": "artist.getSimilar", "limit": limit, "autocorrect": 1}
        if artist_mbid:
            params["mbid"] = artist_mbid
        elif artist_name:
            params["artist"] = artist_name

        data = self._make_request(
            params, use_user_param_in_request=False
        )  # Does not use 'user'

        similar_artists = []
        if data and "similarartists" in data and "artist" in data["similarartists"]:
            raw_artists = data["similarartists"]["artist"]
            if not isinstance(raw_artists, list):
                raw_artists = [raw_artists]
            for artist_data in raw_artists:
                if (
                    "name" in artist_data and "mbid" in artist_data
                ):  # Require name and mbid
                    similar_artists.append(
                        {
                            "name": artist_data["name"],
                            "mbid": artist_data["mbid"],
                            "match_score": artist_data.get("match"),
                        }
                    )
                else:
                    logger.warning(
                        f"Skipping similar artist with missing name or MBID: {artist_data}"
                    )
            logger.info(
                f"Found {len(similar_artists)} artists similar to '{log_identifier}'."
            )
        else:
            logger.warning(
                f"Could not fetch similar artists for '{log_identifier}'. Response: {data}"
            )
        return similar_artists

    def get_artist_top_albums(
        self, artist_name: str = None, artist_mbid: str = None, limit: int = 5
    ) -> list[dict]:
        """Fetches top albums for a given artist, by name or MBID."""
        if not self.api_key:
            logger.warning("Last.fm not configured for get_artist_top_albums.")
            return []
        if not artist_name and not artist_mbid:
            logger.error("Artist name or MBID required for get_artist_top_albums.")
            return []

        log_identifier = artist_mbid if artist_mbid else artist_name
        logger.info(f"Fetching top {limit} albums for artist '{log_identifier}'...")
        params = {"method": "artist.getTopAlbums", "limit": limit, "autocorrect": 1}
        if artist_mbid:
            params["mbid"] = artist_mbid
        elif artist_name:
            params["artist"] = artist_name

        data = self._make_request(params, use_user_param_in_request=False)

        top_albums = []
        if data and "topalbums" in data and "album" in data["topalbums"]:
            raw_albums = data["topalbums"]["album"]
            if not isinstance(raw_albums, list):
                raw_albums = [raw_albums]
            for album_data in raw_albums:
                # Album MBID is important for MusicBrainz lookup later
                if (
                    "name" in album_data
                    and "artist" in album_data
                    and "name" in album_data["artist"]
                    and "mbid" in album_data
                ):
                    top_albums.append(
                        {
                            "name": album_data["name"],
                            "artist": album_data["artist"]["name"],
                            "mbid": album_data[
                                "mbid"
                            ],  # This is album MBID, might be release or release group
                            "playcount": album_data.get("playcount"),
                        }
                    )
                else:
                    logger.warning(
                        f"Skipping top album with missing name, artist, or MBID: {album_data}"
                    )
            logger.info(
                f"Found {len(top_albums)} top albums for artist '{log_identifier}'."
            )
        else:
            logger.warning(
                f"Could not fetch top albums for artist '{log_identifier}'. Response: {data}"
            )
        return top_albums

    def get_album_info(
        self, artist_name: str, album_name: str, mbid: str = None
    ) -> dict | None:
        """Fetches detailed information for a specific album, by artist/album name or MBID."""
        if not self.api_key:
            logger.warning("Last.fm not configured for get_album_info.")
            return None
        if not mbid and (not artist_name or not album_name):
            logger.error(
                "Album MBID or both Artist/Album name required for get_album_info."
            )
            return None

        log_identifier = mbid if mbid else f"{artist_name} - {album_name}"
        logger.info(f"Fetching info for album '{log_identifier}'...")
        params = {"method": "album.getInfo", "autocorrect": 1}
        if mbid:
            params["mbid"] = mbid
        elif artist_name and album_name:
            params["artist"] = artist_name
            params["album"] = album_name

        data = self._make_request(
            params, use_user_param_in_request=bool(self.api_user)
        )  # User param can provide user playcount for album

        if data and "album" in data:
            album_info = data["album"]
            # Extract key details: name, artist, mbid (release group usually), tags, tracks
            # Last.fm's mbid for an album from album.getInfo is usually the Release Group MBID.
            # Tags are under album_info.get('tags', {}).get('tag', [])
            # Each tag is a dict {'name': 'tagName', 'url': '...'}
            logger.info(f"Successfully fetched info for album '{log_identifier}'.")
            return album_info  # Return the full album object from Last.fm
        else:
            logger.warning(
                f"Could not fetch info for album '{log_identifier}'. Response: {data}"
            )
            return None
