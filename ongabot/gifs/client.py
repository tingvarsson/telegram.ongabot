"""Thin async client for the Giphy search API.

This module is I/O only - it searches for GIFs matching a phrase and returns the mp4 rendition
Telegram can play, and knows nothing about moods, chats or which GIF to pick. See
ongabot.gifs.picker for that.

A GIF only ever decorates a message that goes out anyway, so the client is built to fail fast
and quietly: one attempt, a short timeout, and None instead of an exception. The free beta key
allows 100 calls an hour; the picker's per-phrase cache keeps the bot far below that.
"""

import functools
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

_logger = logging.getLogger(__name__)

BASE_URL = "https://api.giphy.com/v1/gifs"

# Short, since a vote reply or poke waits on the search before it is sent.
TIMEOUT_SECONDS = 5.0
# Giphy's content rating cap. The group is adults, but the bot posts unprompted.
RATING = "pg-13"
# How many results one search returns to pick from.
SEARCH_LIMIT = 25
# Telegram fetches an animation sent by URL itself, and refuses files over 20 MB.
MAX_MP4_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Gif:
    """One search hit: its Giphy id and the mp4 rendition Telegram plays as an animation."""

    gif_id: str
    mp4_url: str


def _parse_gif(raw: Dict[str, Any]) -> Optional[Gif]:
    """Parse one search hit, or None when it has no usable mp4.

    Stickers and some old uploads have no mp4 rendition, and a few originals are too big for
    Telegram to fetch. A missing mp4_size is not taken to mean too big.
    """
    original = raw["images"]["original"]
    mp4_url = original.get("mp4")
    if not mp4_url:
        return None
    size = original.get("mp4_size")
    if size is not None and int(size) > MAX_MP4_BYTES:
        return None
    return Gif(gif_id=str(raw["id"]), mp4_url=str(mp4_url))


class GiphyClient:
    """Async Giphy search client that never raises on failure.

    search returns None when results could not be fetched or understood, so an outage or rate
    limit degrades into a text-only message rather than an exception in a handler. Requires a
    beta or production API key from developers.giphy.com, set via GIPHY_API_KEY.
    """

    def __init__(self, api_key: Optional[str], base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        # Created on first use so constructing a client never opens a connection pool, and so
        # tests can substitute their own transport before anything is allocated.
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def has_key(self) -> bool:
        """Whether an API key is set, without which every search comes back empty-handed."""
        return bool(self._api_key)

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

    async def search(self, query: str) -> Optional[List[Gif]]:
        """Search GIFs for query, most relevant first, or None if unavailable.

        An empty list means Giphy answered but had nothing usable for the query.
        """
        if not self._api_key:
            _logger.debug("No GIPHY_API_KEY; skipping GIF search for query=%r", query)
            return None

        params = {"api_key": self._api_key, "q": query, "rating": RATING, "limit": str(SEARCH_LIMIT)}
        try:
            response = await self._http().get(f"{self._base_url}/search", params=params, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as e:
            _logger.warning("Giphy search failed for query=%r: %s", query, e)
            return None
        if response.status_code >= 400:
            _logger.warning("Giphy returned HTTP %d for query=%r", response.status_code, query)
            return None

        try:
            payload = response.json()
        except ValueError as e:
            _logger.warning("Giphy returned malformed JSON for query=%r: %s", query, e)
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            _logger.warning("Giphy search response for query=%r was not the expected shape", query)
            return None

        results = []
        for raw in payload["data"]:
            try:
                gif = _parse_gif(raw)
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                _logger.debug("Skipping unparseable Giphy result for query=%r: %s", query, e)
                continue
            if gif is not None:
                results.append(gif)
        _logger.debug("Giphy search for query=%r returned %d usable result(s)", query, len(results))
        return results


@functools.lru_cache(maxsize=1)
def get_client() -> GiphyClient:
    """Return the process-wide GiphyClient, so one connection pool is shared.

    Deliberately not stored on BotData: that object is pickled by PicklePersistence, and an
    httpx client is not picklable. GIPHY_API_KEY is read once, on first use - main() makes that
    first use happen at startup, so a missing key is reported right away.
    """
    api_key = os.getenv("GIPHY_API_KEY") or None
    if not api_key:
        _logger.warning("GIPHY_API_KEY is not set; the bot's big moments will go out without GIFs")
    return GiphyClient(api_key=api_key)
