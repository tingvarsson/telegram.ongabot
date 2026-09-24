"""Thin async client for Steam's public news feed, narrowed to CS2 patch notes.

I/O only, like cs2.leetify: it knows how to fetch GetNewsForApp and pick the patch-note posts
out of it, and nothing about chats or rendering. See cs2.patchnotesformat for presentation.

The CS2 feed mixes Valve's own patch notes with Valve blog/esports posts and syndicated
third-party articles (PC Gamer, GamingOnLinux, ...). Valve tags its patch notes "patchnotes";
the title fallback exists only for a Valve post that goes out untagged.

No API key is needed for this endpoint.
"""

import functools
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

_logger = logging.getLogger(__name__)

BASE_URL = "https://api.steampowered.com"
APPID_CS2 = 730

# Steam answers in well under a second; a slow reply is better retried on the next poll than
# held open inside the job queue.
TIMEOUT_SECONDS = 10.0
# One retry only. The caller polls repeatedly, so a transient blip is picked up next time.
MAX_ATTEMPTS = 2
# The feed is newest-first. Valve posts several patch notes a week among other news, so 30
# items reach back weeks - far more than can land between two polls.
DEFAULT_COUNT = 30

_PATCHNOTES_TAG = "patchnotes"
_VALVE_FEED = "steam_community_announcements"
_TITLE_FALLBACK_RE = re.compile(r"^Counter-Strike 2 Update\b", re.IGNORECASE)


@dataclass(frozen=True)
class SteamNewsItem:
    """One patch-note post, under Steam's own field names."""

    gid: str  # opaque Steam id: an identity/dedup key only, never an ordering (use date)
    title: str
    url: str
    contents: str  # raw Steam BBCode, see cs2.bbcode
    date: int  # unix timestamp
    tags: Tuple[str, ...]


def _parse_item(raw: Dict[str, Any]) -> SteamNewsItem:
    return SteamNewsItem(
        gid=str(raw["gid"]),
        title=str(raw["title"]),
        url=str(raw["url"]),
        contents=str(raw.get("contents") or ""),
        date=int(raw["date"]),
        tags=tuple(str(tag) for tag in raw.get("tags") or []),
    )


def _is_patch_notes(raw: Dict[str, Any]) -> bool:
    """True if a news item is a CS2 patch-notes post rather than other CS2 news."""
    if _PATCHNOTES_TAG in {str(tag).lower() for tag in raw.get("tags") or []}:
        return True
    # Title alone is not enough: a syndicated article can be titled the same way.
    if raw.get("feedname") == _VALVE_FEED and _TITLE_FALLBACK_RE.match(str(raw.get("title") or "")):
        _logger.info("Steam news gid=%s classified as patch notes by title, not by tag", raw.get("gid"))
        return True
    return False


class SteamNewsClient:
    """Async Steam news client that never raises on failure.

    get_cs2_patch_notes returns None when the feed could not be fetched or understood, so an
    outage degrades into "nothing to announce this poll" rather than breaking the job.
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
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._http().get(url, params=params)
            except httpx.HTTPError as e:
                _logger.warning("Steam news request failed (attempt %d): %s", attempt, e)
                continue

            if response.status_code >= 400:
                _logger.warning("Steam news returned HTTP %d (attempt %d)", response.status_code, attempt)
                continue

            try:
                return response.json()
            except ValueError as e:
                _logger.warning("Steam news returned malformed JSON: %s", e)
                return None

        return None

    async def get_cs2_patch_notes(self, count: int = DEFAULT_COUNT) -> Optional[List[SteamNewsItem]]:
        """Return the recent CS2 patch-note posts, newest first, or None if unavailable.

        None means the feed could not be read - callers must treat it as "nothing to report
        this poll", never as "there are no patch notes". An item that cannot be parsed is
        skipped with a warning rather than failing the whole feed, so one odd post cannot
        block every other announcement until it scrolls off.
        """
        params = {"appid": str(APPID_CS2), "count": str(count), "format": "json"}
        payload = await self._get("/ISteamNews/GetNewsForApp/v2/", params)
        if payload is None:
            return None

        try:
            raw_items = payload["appnews"]["newsitems"]
        except (KeyError, TypeError):
            _logger.warning("Steam news payload had no appnews.newsitems")
            return None
        if not isinstance(raw_items, list):
            _logger.warning("Steam news appnews.newsitems was not a list")
            return None

        items: List[SteamNewsItem] = []
        for raw in raw_items:
            try:
                if _is_patch_notes(raw):
                    items.append(_parse_item(raw))
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                _logger.warning("Skipping unparseable Steam news item: %s", e)

        _logger.debug("Steam news: %d of %d item(s) are CS2 patch notes", len(items), len(raw_items))
        return items


@functools.lru_cache(maxsize=1)
def get_client() -> SteamNewsClient:
    """Return the process-wide SteamNewsClient, so one connection pool is shared.

    Deliberately not stored on BotData: that object is pickled by PicklePersistence, and an
    httpx client is not picklable.
    """
    return SteamNewsClient()
