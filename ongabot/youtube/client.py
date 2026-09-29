"""Thin async client for the YouTube Data API v3.

This module is I/O only - it knows how to search for candidate videos and fetch the fields
needed to confirm one is an actual Short and rank it, and nothing about chats or ranking
policy. See ongabot.youtube.selection for the domain logic.

Two calls carry the whole feature:

* ``search.list`` finds candidates, most-viewed first, optionally limited to a query, a
  publish window and a category. ``videoDuration=short`` (<4 min) is only a coarse
  pre-filter - the API has no "is this a Short" flag.
* ``videos.list`` confirms the real length via ``contentDetails.duration``, returns the view
  count from ``statistics`` and flags live/upcoming broadcasts via
  ``snippet.liveBroadcastContent``.

search.list costs 100 quota units per call, videos.list costs 1, against a default 10,000/day
quota. Searches run on demand from /short, so ongabot.youtube.selection caches ranked results
in-process for a few hours - repeated /short calls walk down a cached list instead of spending
another 100 units each.
"""

import functools
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

_logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/youtube/v3"

TIMEOUT_SECONDS = 10.0
# One retry only. The caller is a user waiting on /short, so a transient blip is better
# answered with "try again in a bit" than by hammering the API.
MAX_ATTEMPTS = 2

_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def _parse_iso8601_duration(duration: str) -> Optional[int]:
    """Parse an ISO-8601 duration like "PT1M5S" into whole seconds, or None if malformed."""
    match = _DURATION_RE.match(duration or "")
    if match is None:
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _rfc3339_utc(moment: datetime) -> str:
    """Format a datetime as the RFC 3339 UTC timestamp publishedAfter expects ("...Z").

    A naive datetime is taken to already be UTC.
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def _parse_view_count(statistics: Dict[str, Any]) -> int:
    """Return statistics.viewCount as an int, or 0 when missing, hidden or malformed."""
    try:
        return int(statistics.get("viewCount") or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class SearchResult:
    """One search.list hit - just enough to decide whether to look closer."""

    video_id: str
    title: str


@dataclass(frozen=True)
class VideoDetail:
    """A videos.list entry - what's needed to confirm a Short and rank it."""

    video_id: str
    title: str
    tags: Tuple[str, ...]
    duration_seconds: int
    # 0 when the uploader hides the count or statistics are missing, so such videos rank last.
    view_count: int = 0
    # True for live and upcoming broadcasts (liveBroadcastContent other than "none").
    live: bool = False


def _parse_search_result(raw: Dict[str, Any]) -> SearchResult:
    return SearchResult(
        video_id=str(raw["id"]["videoId"]),
        title=str(raw.get("snippet", {}).get("title") or ""),
    )


def _parse_video_detail(raw: Dict[str, Any]) -> VideoDetail:
    snippet = raw.get("snippet") or {}
    content_details = raw.get("contentDetails") or {}
    statistics = raw.get("statistics") or {}
    duration = _parse_iso8601_duration(str(content_details["duration"]))
    if duration is None:
        raise ValueError(f"unparseable duration: {content_details.get('duration')!r}")
    return VideoDetail(
        video_id=str(raw["id"]),
        title=str(snippet.get("title") or ""),
        tags=tuple(str(tag) for tag in snippet.get("tags") or ()),
        duration_seconds=duration,
        view_count=_parse_view_count(statistics),
        live=str(snippet.get("liveBroadcastContent") or "none") != "none",
    )


class YouTubeClient:
    """Async YouTube Data API v3 client that never raises on failure.

    Every method returns None when the data could not be fetched or understood, so an API
    outage or quota exhaustion degrades into a "couldn't reach YouTube" reply to /short rather
    than an exception in the handler. Requires an API key - console.cloud.google.com, enable
    "YouTube Data API v3" - set via YOUTUBE_API_KEY.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
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
        request_params = dict(params)
        if self._api_key:
            request_params["key"] = self._api_key

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._http().get(url, params=request_params, timeout=TIMEOUT_SECONDS)
            except httpx.HTTPError as e:
                _logger.warning("YouTube request failed (attempt %d) for %s: %s", attempt, path, e)
                continue

            if response.status_code >= 400:
                _logger.warning("YouTube returned HTTP %d (attempt %d) for %s", response.status_code, attempt, path)
                continue

            try:
                return response.json()
            except ValueError as e:
                _logger.warning("YouTube returned malformed JSON for %s: %s", path, e)
                return None

        return None

    async def search_shorts(
        self,
        query: str,
        *,
        order: str = "viewCount",
        published_after: Optional[datetime] = None,
        category_id: Optional[str] = None,
        max_results: int = 50,
    ) -> Optional[List[SearchResult]]:
        """Search for candidate Shorts, or None if unavailable.

        An empty query leaves out ``q`` so the search spans everything matching the other
        filters (e.g. a whole category). published_after limits results to videos published
        since then, and category_id to one videoCategoryId.
        """
        params = {
            "part": "snippet",
            "type": "video",
            "videoDuration": "short",
            "safeSearch": "strict",
            "order": order,
            "maxResults": str(max_results),
        }
        if query:
            params["q"] = query
        if published_after is not None:
            params["publishedAfter"] = _rfc3339_utc(published_after)
        if category_id is not None:
            params["videoCategoryId"] = category_id
        _logger.debug(
            "YouTube search query=%r order=%s publishedAfter=%s category=%s maxResults=%d",
            query,
            order,
            params.get("publishedAfter"),
            category_id,
            max_results,
        )

        payload = await self._get("/search", params)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            if payload is not None:
                _logger.warning("YouTube search response for query=%r was not the expected shape", query)
            return None

        try:
            results = [_parse_search_result(raw) for raw in payload["items"]]
        except (KeyError, TypeError, ValueError) as e:
            _logger.warning("Could not parse YouTube search results for query=%r: %s", query, e)
            return None

        _logger.debug("YouTube search for query=%r returned %d result(s)", query, len(results))
        return results

    async def get_video_details(self, video_ids: Sequence[str]) -> Optional[Dict[str, VideoDetail]]:
        """Return duration/views/live state/title for each id in one batched call, or None if unavailable.

        videos.list takes at most 50 ids per call, which matches search_shorts' max_results.
        """
        if not video_ids:
            return {}

        payload = await self._get(
            "/videos",
            {"part": "snippet,contentDetails,statistics", "id": ",".join(video_ids)},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            if payload is not None:
                _logger.warning("YouTube videos response was not the expected shape")
            return None

        try:
            details = {d.video_id: d for d in (_parse_video_detail(raw) for raw in payload["items"])}
        except (KeyError, TypeError, ValueError) as e:
            _logger.warning("Could not parse YouTube video details: %s", e)
            return None

        _logger.debug("YouTube videos.list returned details for %d/%d id(s)", len(details), len(video_ids))
        return details


@functools.lru_cache(maxsize=1)
def get_client() -> YouTubeClient:
    """Return the process-wide YouTubeClient, so one connection pool is shared.

    Deliberately not stored on BotData: that object is pickled by PicklePersistence, and an
    httpx client is not picklable. YOUTUBE_API_KEY is read once, on first use.
    """
    api_key = os.getenv("YOUTUBE_API_KEY") or None
    if not api_key:
        _logger.error("YOUTUBE_API_KEY is not set; YouTube Short requests will fail")
    return YouTubeClient(api_key=api_key)
