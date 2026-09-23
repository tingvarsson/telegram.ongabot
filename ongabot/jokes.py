"""Thin async client for the JokeAPI public API (https://v2.jokeapi.dev/), used to source
dynamic quip lines rather than a fixed, hand-written list.

Requests ask for one-line jokes only, from categories that exclude "Dark", and with every
sensitive content flag blacklisted - a "safe" filter is applied again client-side since
JokeAPI's own blacklist is best-effort. No API key is required.
"""

import functools
import logging
from typing import Any, Dict, List, Optional

import httpx

_logger = logging.getLogger(__name__)

BASE_URL = "https://v2.jokeapi.dev"
# "Dark" is deliberately excluded from the category list, on top of the flag blacklist below.
CATEGORIES = "Programming,Miscellaneous,Pun,Spooky,Christmas"
BLACKLIST_FLAGS = "nsfw,religious,political,racist,sexist,explicit"
# JokeAPI answers in well under a second; a slow reply means something is wrong upstream and
# the refresh job is better off retrying on its next pass than holding the job queue open.
TIMEOUT_SECONDS = 10.0
# One retry only. The caller is a repeating job, so a transient blip is picked up on the next
# pass anyway - hammering a keyless public API buys nothing.
MAX_ATTEMPTS = 2
# JokeAPI's own per-request cap.
MAX_AMOUNT = 10


class JokeApiClient:
    """Async JokeAPI client that never raises on failure.

    fetch_jokes returns None when the jokes could not be fetched or understood, so an outage
    degrades into "keep using the existing quip pool" rather than breaking the refresh job.
    """

    def __init__(self, base_url: str = BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        # Created on first use so constructing a client never opens a connection pool, and so
        # tests can substitute their own transport before anything is allocated.
        self._client: Optional[httpx.AsyncClient] = None

    def _http(self) -> httpx.AsyncClient:
        """Return the shared AsyncClient, creating it on first use."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: Dict[str, str]) -> Optional[Any]:
        """GET a path and return decoded JSON, or None on any failure whatsoever."""
        url = f"{self._base_url}{path}"
        headers = {"Accept": "application/json"}

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._http().get(url, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
            except httpx.HTTPError as e:
                _logger.warning("JokeAPI request failed (attempt %d) for %s: %s", attempt, path, e)
                continue

            if response.status_code >= 400:
                _logger.warning("JokeAPI returned HTTP %d (attempt %d) for %s", response.status_code, attempt, path)
                continue

            try:
                return response.json()
            except ValueError as e:
                _logger.warning("JokeAPI returned malformed JSON for %s: %s", path, e)
                return None

        return None

    async def fetch_jokes(self, amount: int = MAX_AMOUNT) -> Optional[List[str]]:
        """Fetch up to `amount` short, safe jokes as plain single-line strings.

        Returns None if the request failed outright or the response could not be understood.
        An empty list is a valid, successful result (JokeAPI had nothing matching right now).
        """
        params = {
            "type": "single",
            "blacklistFlags": BLACKLIST_FLAGS,
            "amount": str(min(amount, MAX_AMOUNT)),
        }
        payload = await self._get(f"/joke/{CATEGORIES}", params)
        if not isinstance(payload, dict):
            return None
        if payload.get("error"):
            _logger.warning("JokeAPI reported an error: %s", payload.get("message"))
            return None

        raw_jokes = payload.get("jokes")
        if not isinstance(raw_jokes, list):
            _logger.warning("JokeAPI response had no 'jokes' list: %s", payload)
            return None

        jokes = [
            " ".join(str(raw["joke"]).split())
            for raw in raw_jokes
            if isinstance(raw, dict) and raw.get("safe") and raw.get("joke")
        ]
        _logger.debug("JokeAPI returned %d usable joke(s) out of %d fetched", len(jokes), len(raw_jokes))
        return jokes


@functools.lru_cache(maxsize=1)
def get_client() -> JokeApiClient:
    """Return the process-wide JokeApiClient, so one connection pool is shared."""
    return JokeApiClient()
